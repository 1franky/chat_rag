"""Bootstrap de Celery para chat_rag.

El worker real (tasks de ingesta) se implementa en la Fase 3. Este módulo
solo deja la app de Celery lista, apuntando a Redis como broker/backend vía
REDIS_URL (ver .env.example), y con autodiscover de tasks en las apps
instaladas.
"""

import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("chat_rag")
app.conf.broker_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
app.conf.result_backend = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
