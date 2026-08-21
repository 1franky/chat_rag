"""Logging estructurado (JSON) compartido entre chat-web y chat-rag-mcp
(plan.md, Fase 7).

Enruta TANTO structlog como el logging estándar de Python (el que ya usa
`logging.getLogger(__name__)` en ingesta/tasks.py, Django, Celery, uvicorn,
etc.) por el mismo pipeline, así que llamar `configure_logging()` una vez
al arrancar el proceso alcanza para que TODO el logging del proyecto salga
en JSON por stdout — no hace falta reescribir los `logger.info(...)` que ya
existen a la API de structlog.

Se escribe a stdout sin manejo de archivos/rotación propio a propósito: en
Docker, stdout ya lo captura el logging driver `json-file`, configurado con
`max-size`/`max-file` en compose.yaml — es lo que rota los logs acá, no
logrotate (que apunta a archivos en filesystem, no aplica bien a contenedores
con `read_only: true`).
"""

from __future__ import annotations

import logging
import os
import sys

import structlog


def configure_logging(*, service: str) -> None:
    """Llamar una sola vez, lo antes posible al arrancar el proceso.

    `service` se agrega como campo fijo en cada línea de log (`chat-web`,
    `chat-worker`, `chat-rag-mcp`) para poder filtrar/separar cuando los
    tres procesos loguean al mismo `docker compose logs`.
    """
    level_name = os.environ.get("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    # JSON_LOGS=0 (ej. para `manage.py runserver` en desarrollo local) usa
    # el renderer de consola de structlog (coloreado, legible) en vez de JSON.
    json_output = os.environ.get("JSON_LOGS", "1") == "1"

    timestamper = structlog.processors.TimeStamper(fmt="iso", utc=True)
    shared_processors: list = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        timestamper,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    structlog.configure(
        processors=[*shared_processors, structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    renderer = structlog.processors.JSONRenderer() if json_output else structlog.dev.ConsoleRenderer()
    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
        foreign_pre_chain=[*shared_processors, structlog.stdlib.add_log_level],
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers = [handler]
    root_logger.setLevel(level)

    # uvicorn (chat-web) configura sus propios handlers para "uvicorn",
    # "uvicorn.access" y "uvicorn.error" ANTES de que esto corra (arranca,
    # loguea el banner, RECIÉN AHÍ importa la app ASGI — que es cuando
    # config.settings, y por lo tanto esto, se ejecuta) — sin vaciarlos acá,
    # esos tres loggers en particular ignoran el handler de arriba y siguen
    # imprimiendo texto plano aunque root_logger ya esté en JSON.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uv_logger = logging.getLogger(name)
        uv_logger.handlers = []
        uv_logger.propagate = True

    structlog.contextvars.bind_contextvars(service=service)
