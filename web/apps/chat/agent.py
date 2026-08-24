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
    "Eres el asistente de chat_rag, una plataforma de chat personal con RAG. "
    "Tienes tres grupos de tools disponibles vía MCP: las de `data-platform` "
    "para consultar bases de datos conectadas, las de `rag` "
    "(rag_search, rag_list_documents, rag_get_document_chunks, "
    "rag_list_collections) para buscar en los documentos que el usuario "
    "subió, y las de reportería (report_generate_table, por ahora) para "
    "generar archivos descargables. Usa rag_search antes de responder "
    "cualquier pregunta sobre el "
    "contenido de esos documentos — no asumas que no hay nada indexado sin "
    "buscar primero. Los documentos pueden estar agrupados en colecciones "
    "(carpetas); usa rag_list_collections si no sabés cuáles existen, y "
    "pasale el parámetro `collection` a rag_search SOLO cuando el usuario "
    "pida explícitamente acotar la búsqueda a una en particular (ej. "
    "'buscá solo en Contratos 2026') — por default buscá en todo lo "
    "indexado, sin filtrar por colección. "
    "Cuando el usuario pida explícitamente un archivo/reporte/exportar "
    "datos (ej. 'dame esto en un Excel', 'expórtamelo', 'quiero un "
    "archivo con...') en vez de verlos en el chat, arma los datos vos "
    "mismo (con las tools de data-platform o rag_search según corresponda) "
    "y usa report_generate_table para generarlo — es la única tool para "
    "esto. `generate_report` de `data-platform`, si aparece disponible, "
    "NO se usa nunca: es una tool de otro proyecto que quedó acotado solo "
    "a consultar datos. Para pedidos normales de datos/búsqueda sin "
    "mención de archivo, responde en el chat como siempre, sin generar "
    "ningún archivo. Responde "
    "siempre en español neutro/mexicano (el usuario está en México): usa "
    "'tú' en vez de 'vos' — nunca 'sos', 'tenés', 'usá', 'respondé', "
    "'arrancá' ni ninguna otra conjugación de voseo rioplatense — y de "
    "forma directa y sin relleno."
)


def _build_options(resume: str | None, model: str) -> ClaudeAgentOptions:
    return ClaudeAgentOptions(
        mcp_servers={
            "data-platform": {"type": "http", "url": DATA_PLATFORM_MCP_URL},
            "rag": {"type": "http", "url": RAG_MCP_URL},
        },
        system_prompt=SYSTEM_PROMPT,
        resume=resume or None,
        include_partial_messages=True,
        # Alias del SDK ("sonnet"/"opus", plan-v2.md Fase 13) — elegido al
        # crear la conversación (`Conversation.model`), no un ID pineado.
        model=model,
        # Uso 100% personal (plan.md, sección 2.3): sin UI de aprobación de
        # tools por turno, todas las tools configuradas están ya de por sí
        # acotadas a los dos MCPs propios.
        permission_mode="bypassPermissions",
    )


async def stream_reply(resume_session_id: str | None, user_message: str, model: str) -> AsyncIterator[dict[str, Any]]:
    """Manda `user_message` a Claude y yield-ea eventos serializables:

    - {"type": "token", "text": str} — delta de texto (streaming real)
    - {"type": "tool_use", "id", "name", "input"} — Claude invoca una tool
    - {"type": "tool_result", "tool_use_id", "content", "is_error"}
    - {"type": "done", "session_id", "is_error", "error", "cost_usd"} — fin
      del turno

    `model`: alias del Agent SDK ("sonnet"/"opus") — `Conversation.model`.
    """
    options = _build_options(resume_session_id, model)

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
                # ID(s) de modelo real que resolvió el alias pedido
                # (plan-v2.md, Fase 13) — solo para loguear y poder
                # verificar que Opus/Sonnet efectivamente se usó, no para
                # mostrar en la UI.
                "resolved_model": list(message.model_usage) if message.model_usage else None,
                # Costo real del turno en USD (plan-v3.md, Fase 14) — se
                # acumula en Conversation.total_cost_usd. None en turnos que
                # fallaron antes de completar (visto como 0 por quien suma).
                "cost_usd": message.total_cost_usd,
            }
