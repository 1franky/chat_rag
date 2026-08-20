from django.contrib import admin
from django.urls import include, path

from apps.core.views import root

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", root, name="root"),
    path("", include("apps.core.urls")),
    path("chat/", include("apps.chat.urls")),
    path("documentos/", include("apps.ingesta.urls")),
    path("", include("apps.accounts.urls")),
]
