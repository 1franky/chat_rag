from django.contrib import admin
from django.urls import include, path

from apps.chat.views import shared_conversation
from apps.core.views import root

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", root, name="root"),
    path("", include("apps.core.urls")),
    path("chat/", include("apps.chat.urls")),
    path("documentos/", include("apps.ingesta.urls")),
    # Fuera del namespace `chat:` (Fase 11, plan-v2.md) — es la vista PÚBLICA
    # de solo lectura, sin login, en su propio prefijo (ver
    # apps/core/middlewares.py::EXEMPT_PATH_PREFIXES).
    path("compartido/<str:token>/", shared_conversation, name="shared_conversation"),
    path("", include("apps.accounts.urls")),
]
