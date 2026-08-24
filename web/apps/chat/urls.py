from django.urls import path

from . import views

app_name = "chat"

urlpatterns = [
    path("", views.home, name="home"),
    path("nueva/", views.new_conversation, name="new"),
    path("buscar/", views.search_conversations, name="search"),
    path("<uuid:conversation_id>/", views.conversation_detail, name="detail"),
    path("<uuid:conversation_id>/stream/", views.stream_message, name="stream"),
    path("<uuid:conversation_id>/reintentar/", views.retry_message, name="retry"),
    path("<uuid:conversation_id>/borrar/", views.delete_conversation, name="delete"),
    path("<uuid:conversation_id>/exportar/", views.export_conversation, name="export"),
    path("<uuid:conversation_id>/compartir/", views.share_conversation, name="share"),
    path("<uuid:conversation_id>/compartir/revocar/", views.revoke_share, name="revoke_share"),
]
