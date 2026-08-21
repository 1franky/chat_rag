from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.views.decorators.http import require_GET, require_POST

from .models import Document
from .services import delete_document
from .tasks import process_document


@login_required
def list_documents(request: HttpRequest) -> HttpResponse:
    documents = Document.objects.active()
    return render(request, "ingesta/documents.html", {"documents": documents})


@login_required
@require_POST
def upload(request: HttpRequest) -> JsonResponse:
    uploaded = request.FILES.get("file")
    if not uploaded:
        return JsonResponse({"error": "No se recibió ningún archivo"}, status=400)

    document = Document.objects.create(
        filename=uploaded.name,
        file=uploaded,
        mime_type=uploaded.content_type or "",
        size=uploaded.size,
    )
    process_document.delay(str(document.id))

    card_html = render_to_string("ingesta/_document_card.html", {"document": document}, request=request)
    return JsonResponse({"document_id": str(document.id), "card_html": card_html})


@login_required
@require_GET
def status(request: HttpRequest, document_id) -> HttpResponse:
    """Fragmento HTML de una card, para el polling de htmx (hx-swap=outerHTML)."""
    document = get_object_or_404(Document.objects.active(), pk=document_id)
    return render(request, "ingesta/_document_card.html", {"document": document})


@login_required
@require_POST
def delete(request: HttpRequest, document_id) -> HttpResponse:
    document = get_object_or_404(Document.objects.active(), pk=document_id)
    delete_document(document)
    return redirect("ingesta:list")
