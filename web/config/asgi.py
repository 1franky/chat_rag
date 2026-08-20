"""
ASGI config for config project.

Expone el callable ASGI como `application`, servido por Daphne. El chat
(Fase 4) usa Server-Sent Events sobre vistas async normales de Django, así
que por ahora el router solo envuelve el protocolo `http`; si más adelante
se necesita WebSockets, se agrega aquí un `URLRouter` para el protocolo `ws`.

For more information on this file, see
https://docs.djangoproject.com/en/5.0/howto/deployment/asgi/
"""

import os

from channels.routing import ProtocolTypeRouter
from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

application = ProtocolTypeRouter(
    {
        "http": get_asgi_application(),
    }
)
