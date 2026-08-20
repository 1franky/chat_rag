"""Wrapper del Agent SDK (plan.md, sección 2.3 y Fase 4).

`stream_reply` envuelve `claude_agent_sdk.query()` en un generador async que
yield-ea eventos ya serializables para mandar por SSE. Se usa `query()` (no
`ClaudeSDKClient`) a propósito: cada request HTTP de Django es su propio
proceso stateless, así que no hay dónde mantener viva una conexión — en
cambio, cada turno resume la conversación anterior por `session_id`
(`ClaudeAgentOptions.resume`), que el SDK reconstruye leyendo el transcript
guardado en CLAUDE_CONFIG_DIR (ver entrypoint.sh).
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from typing import Any

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
    StreamEvent,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
    query,
)

DATA_PLATFORM_MCP_URL = os.environ.get("DATA_PLATFORM_MCP_URL", "http://data-platform-mcp:8000/mcp")
RAG_MCP_URL = os.environ.get("RAG_MCP_URL", "http://chat-rag-mcp:8100/mcp")

SYSTEM_PROMPT = (
    "Sos el asistente de chat_rag, una plataforma de chat personal con RAG. "
    "Tenés dos grupos de tools disponibles vía MCP: las de `data-platform` "
    "para consultar bases de datos conectadas, y las de `rag` "
    "(rag_search, rag_list_documents, rag_get_document_chunks) para buscar "
    "en los documentos que el usuario subió. Usá rag_search antes de "
    "responder cualquier pregunta sobre el contenido de esos documentos — "
    "no asumas que no hay nada indexado sin buscar primero. Respondé "
    "siempre en español, de forma directa y sin relleno."
)


def _build_options(resume: str | None) -> ClaudeAgentOptions:
    return ClaudeAgentOptions(
        mcp_servers={
            "data-platform": {"type": "http", "url": DATA_PLATFORM_MCP_URL},
            "rag": {"type": "http", "url": RAG_MCP_URL},
        },
        system_prompt=SYSTEM_PROMPT,
        resume=resume or None,
        include_partial_messages=True,
        # Uso 100% personal (plan.md, sección 2.3): sin UI de aprobación de
        # tools por turno, todas las tools configuradas están ya de por sí
        # acotadas a los dos MCPs propios.
        permission_mode="bypassPermissions",
    )


async def stream_reply(resume_session_id: str | None, user_message: str) -> AsyncIterator[dict[str, Any]]:
    """Manda `user_message` a Claude y yield-ea eventos serializables:

    - {"type": "token", "text": str} — delta de texto (streaming real)
    - {"type": "tool_use", "id", "name", "input"} — Claude invoca una tool
    - {"type": "tool_result", "tool_use_id", "content", "is_error"}
    - {"type": "done", "session_id", "is_error", "error"} — fin del turno
    """
    options = _build_options(resume_session_id)

    async for message in query(prompt=user_message, options=options):
        if isinstance(message, StreamEvent):
            delta = message.event.get("delta", {})
            if message.event.get("type") == "content_block_delta" and delta.get("type") == "text_delta":
                yield {"type": "token", "text": delta["text"]}

        elif isinstance(message, AssistantMessage | UserMessage):
            for block in message.content:
                if isinstance(block, ToolUseBlock):
                    yield {"type": "tool_use", "id": block.id, "name": block.name, "input": block.input}
                elif isinstance(block, ToolResultBlock):
                    yield {
                        "type": "tool_result",
                        "tool_use_id": block.tool_use_id,
                        "content": block.content,
                        "is_error": bool(block.is_error),
                    }
                elif isinstance(block, TextBlock) and isinstance(message, AssistantMessage):
                    # Texto completo del bloque (autoridad para lo que se
                    # persiste) — los tokens de arriba son solo para el
                    # efecto de "escribiendo" en vivo en el cliente.
                    yield {"type": "text_block", "text": block.text}
            if isinstance(message, AssistantMessage) and message.error:
                yield {"type": "error", "error": message.error}

        elif isinstance(message, ResultMessage):
            yield {
                "type": "done",
                "session_id": message.session_id,
                "is_error": message.is_error,
                "error": message.result if message.is_error else None,
            }
