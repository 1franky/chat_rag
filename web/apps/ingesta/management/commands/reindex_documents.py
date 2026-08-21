"""Management command: migra la colección de Qdrant para agregar sparse
vectors (BM25) y reindexa todos los documentos activos (plan-v2.md, Fase 12
— búsqueda híbrida).

Qdrant no permite agregar un named vector nuevo a una colección ya
existente, así que la única forma de migrar es borrarla y recrearla vacía
—ya con el sparse vector configurado— y volver a encolar la ingesta de cada
documento (parseo, chunking y embeddings ya corren de nuevo desde cero, no
hay forma de "solo agregar" el sparse vector a los puntos existentes).

Uso:
    docker compose exec chat-web python manage.py reindex_documents
    docker compose exec chat-web python manage.py reindex_documents --yes
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from rag_shared.vector_store import collection_has_sparse_vectors_sync, recreate_collection_sync

from ...models import Document
from ...tasks import process_document


class Command(BaseCommand):
    help = "Recrea la colección de Qdrant con sparse vectors y reencola la ingesta de todos los documentos activos."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--yes", action="store_true", help="No pedir confirmación antes de borrar la colección.")
        parser.add_argument(
            "--force",
            action="store_true",
            help="Recrear la colección igual aunque ya tenga sparse vectors configurados.",
        )

    def handle(self, *args, **options) -> None:
        documents = list(Document.objects.active())
        if not documents:
            self.stdout.write("No hay documentos activos, nada que reindexar.")
            return

        if not options["force"] and collection_has_sparse_vectors_sync():
            self.stdout.write(
                self.style.WARNING(
                    "La colección ya tiene sparse vectors configurados — nada que migrar "
                    "(usar --force para recrearla igual)."
                )
            )
            return

        if not options["yes"]:
            confirm = input(
                f"Esto BORRA la colección de Qdrant completa y reencola los {len(documents)} documento(s) "
                "activos para reindexar desde cero. ¿Continuar? [y/N] "
            )
            if confirm.strip().lower() != "y":
                self.stdout.write("Cancelado.")
                return

        self.stdout.write("Recreando la colección de Qdrant (con sparse vectors)...")
        recreate_collection_sync()

        for document in documents:
            process_document.delay(str(document.id))

        self.stdout.write(
            self.style.SUCCESS(
                f"Colección recreada. {len(documents)} documento(s) reencolados para reindexar vía Celery — "
                "seguir el progreso en /documentos/ o en los logs de chat-worker."
            )
        )
