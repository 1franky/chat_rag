"""Bootstrap de Celery para chat_rag.

El worker real (tasks de ingesta) se implementa en la Fase 3. Este módulo
solo deja la app de Celery lista, apuntando a Redis como broker/backend vía
REDIS_URL (ver .env.example), y con autodiscover de tasks en las apps
instaladas.
"""

import os

from celery import Celery
from celery.signals import setup_logging

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("chat_rag")
app.conf.broker_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
app.conf.result_backend = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()


# Sin esto, Celery hijackea el root logger al arrancar el worker (
# worker_hijack_root_logger, default True) y pisa el handler JSON que
# config.settings ya dejó armado (rag_shared.logging.configure_logging) con
# su propio formato de texto plano — conectar la señal `setup_logging` le
# dice a Celery "yo me encargo", así respeta la config existente (plan.md,
# Fase 7: logs estructurados JSON).
@setup_logging.connect
def _skip_celery_logging_setup(**kwargs) -> None:
    pass
