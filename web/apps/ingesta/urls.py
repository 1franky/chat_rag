from django.urls import path

from . import views

app_name = "ingesta"

urlpatterns = [
    path("", views.list_documents, name="list"),
    path("subir/", views.upload, name="upload"),
    path("<uuid:document_id>/estado/", views.status, name="status"),
    path("<uuid:document_id>/borrar/", views.delete, name="delete"),
]
