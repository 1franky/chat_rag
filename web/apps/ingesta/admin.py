from django.contrib import admin

from .models import Collection, Document


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ("filename", "mime_type", "status", "chunk_count", "collection", "uploaded_at")
    list_filter = ("status", "collection")
    search_fields = ("filename",)
    readonly_fields = ("id", "uploaded_at")


@admin.register(Collection)
class CollectionAdmin(admin.ModelAdmin):
    list_display = ("name", "created_at", "updated_at")
    search_fields = ("name",)
    readonly_fields = ("id", "created_at", "updated_at")
