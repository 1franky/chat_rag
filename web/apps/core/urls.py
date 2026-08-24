from django.urls import path

from . import views

app_name = "core"

urlpatterns = [
    path("healthz", views.healthz, name="healthz"),
    path("metrics", views.metrics, name="metrics"),
    # plan-v3.md, Fase 20 — prefijo debe coincidir con REPORTS_URL_PATH en
    # rag-mcp/server.py, que arma este link con PUBLIC_BASE_URL.
    path("reportes/<str:filename>", views.download_report, name="download_report"),
]
