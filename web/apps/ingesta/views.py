from __future__ import annotations

import structlog
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.views.decorators.http import require_GET, require_POST

from . import services
from .models import Collection, Document
from .services import delete_document
from .tasks import process_document

logger = structlog.get_logger()


@login_required
def list_documents(request: HttpRequest) -> HttpResponse:
    collections = Collection.objects.all()
    documents = Document.objects.active().select_related("collection")

    # Filtro por colección (plan-v2.md, Fase 10): "?coleccion=sin-coleccion"
    # es un valor especial (no un UUID válido) para los documentos sin
    # ninguna colección asignada; cualquier otro valor es el id de una
    # Collection real.
    active_collection = None
    filter_param = request.GET.get("coleccion")
    filter_none = filter_param == "sin-coleccion"
    if filter_none:
        documents = documents.filter(collection__isnull=True)
    elif filter_param:
        active_collection = get_object_or_404(Collection, pk=filter_param)
        documents = documents.filter(collection=active_collection)

    return render(
        request,
        "ingesta/documents.html",
        {
            "documents": documents,
            "collections": collections,
            "active_collection": active_collection,
            "filter_none": filter_none,
        },
    )


@login_required
@require_POST
def upload(request: HttpRequest) -> JsonResponse:
    uploaded = request.FILES.get("file")
    if not uploaded:
        return JsonResponse({"error": "No se recibió ningún archivo"}, status=400)

    collection = None
    collection_id = request.POST.get("collection")
    if collection_id:
        collection = get_object_or_404(Collection, pk=collection_id)

    document = Document.objects.create(
        filename=uploaded.name,
        file=uploaded,
        mime_type=uploaded.content_type or "",
        size=uploaded.size,
        collection=collection,
    )
    process_document.delay(str(document.id))
    logger.info("document_uploaded", document_id=str(document.id), filename=document.filename, size=document.size)

    card_html = render_to_string(
        "ingesta/_document_card.html",
        {"document": document, "collections": Collection.objects.all()},
        request=request,
    )
    return JsonResponse({"document_id": str(document.id), "card_html": card_html})


@login_required
@require_GET
def status(request: HttpRequest, document_id) -> HttpResponse:
    """Fragmento HTML de una card, para el polling de htmx (hx-swap=outerHTML)."""
    document = get_object_or_404(Document.objects.active(), pk=document_id)
    return render(
        request,
        "ingesta/_document_card.html",
        {"document": document, "collections": Collection.objects.all()},
    )


@login_required
@require_POST
def delete(request: HttpRequest, document_id) -> HttpResponse:
    document = get_object_or_404(Document.objects.active(), pk=document_id)
    delete_document(document)
    logger.info("document_deleted", document_id=str(document_id), filename=document.filename)
    return redirect("ingesta:list")


@login_required
@require_POST
def move_document(request: HttpRequest, document_id) -> HttpResponse:
    """Mueve un documento a otra colección (o a ninguna) desde el <select>
    de su card — devuelve la card actualizada para el hx-swap."""
    document = get_object_or_404(Document.objects.active(), pk=document_id)
    collection_id = request.POST.get("collection") or None
    collection = get_object_or_404(Collection, pk=collection_id) if collection_id else None
    services.move_document(document, collection)
    logger.info("document_moved", document_id=str(document_id), collection_id=collection_id)
    return render(
        request,
        "ingesta/_document_card.html",
        {"document": document, "collections": Collection.objects.all()},
    )


@login_required
@require_POST
def create_collection(request: HttpRequest) -> HttpResponse:
    name = (request.POST.get("name") or "").strip()
    if name:
        try:
            Collection.objects.create(name=name)
        except IntegrityError:
            messages.error(request, f"Ya existe una colección llamada «{name}».")
    return redirect("ingesta:list")


@login_required
@require_POST
def rename_collection(request: HttpRequest, collection_id) -> HttpResponse:
    collection = get_object_or_404(Collection, pk=collection_id)
    name = (request.POST.get("name") or "").strip()
    if name and name != collection.name:
        collection.name = name
        try:
            collection.save(update_fields=["name", "updated_at"])
        except IntegrityError:
            messages.error(request, f"Ya existe una colección llamada «{name}».")
    return redirect("ingesta:list")


@login_required
@require_POST
def delete_collection(request: HttpRequest, collection_id) -> HttpResponse:
    collection = get_object_or_404(Collection, pk=collection_id)
    name = collection.name
    # SET_NULL en Document.collection: los documentos de la colección no se
    # borran, solo quedan sin colección (ver el FK en ingesta/models.py).
    collection.delete()
    logger.info("collection_deleted", collection_id=str(collection_id), name=name)
    return redirect("ingesta:list")
