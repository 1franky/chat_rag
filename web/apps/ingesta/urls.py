from django.urls import path

from . import views

app_name = "ingesta"

urlpatterns = [
    path("", views.list_documents, name="list"),
    path("subir/", views.upload, name="upload"),
    path("<uuid:document_id>/estado/", views.status, name="status"),
    path("<uuid:document_id>/borrar/", views.delete, name="delete"),
    path("<uuid:document_id>/mover/", views.move_document, name="move"),
    path("colecciones/nueva/", views.create_collection, name="collection_create"),
    path("colecciones/<uuid:collection_id>/renombrar/", views.rename_collection, name="collection_rename"),
    path("colecciones/<uuid:collection_id>/borrar/", views.delete_collection, name="collection_delete"),
]
