from django.contrib import admin

from .models import ImportBatch, ImportRowResult, LegacyObjectMap


@admin.register(ImportBatch)
class ImportBatchAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "kind",
        "status",
        "source_filename",
        "actor",
        "total_rows",
        "error_count",
        "created_at",
    )
    list_filter = ("kind", "status", "mode")
    search_fields = ("source_filename", "source_sha256", "actor__username")
    readonly_fields = (
        "source_sha256",
        "total_rows",
        "created_count",
        "updated_count",
        "skipped_count",
        "error_count",
        "summary",
        "created_at",
        "completed_at",
    )


@admin.register(ImportRowResult)
class ImportRowResultAdmin(admin.ModelAdmin):
    list_display = ("batch", "row_number", "external_key", "action", "message")
    list_filter = ("action", "target_type")
    search_fields = ("external_key", "message")
    readonly_fields = ("safe_data", "created_at")


@admin.register(LegacyObjectMap)
class LegacyObjectMapAdmin(admin.ModelAdmin):
    list_display = ("source_system", "object_type", "external_key", "target_object_id")
    list_filter = ("source_system", "object_type")
    search_fields = ("external_key", "target_object_id")
    readonly_fields = ("created_at", "updated_at")
