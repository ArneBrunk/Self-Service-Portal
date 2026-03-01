from django.contrib import admin
from .models import Document, KBEntry, TempNotice, Chunk

@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "status", "updated_at")
    list_filter = ("status",)
    search_fields = ("title",)

@admin.register(KBEntry)
class KBEntryAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "status", "version", "updated_at")
    list_filter = ("status",)
    search_fields = ("title", "body_md")

@admin.register(TempNotice)
class TempNoticeAdmin(admin.ModelAdmin):
    list_display = ("title", "mode", "scope", "priority", "starts_at", "ends_at", "enabled")
    list_filter = ("mode", "enabled")
    search_fields = ("title", "body")

@admin.register(Chunk)
class ChunkAdmin(admin.ModelAdmin):
    list_display = ("id", "source_kind", "source_id", "ord")
    list_filter = ("source_kind",)
    search_fields = ("text",)
