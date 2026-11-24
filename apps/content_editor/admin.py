from django.contrib import admin

from .models import PastedImage


@admin.register(PastedImage)
class PastedImageAdmin(admin.ModelAdmin):
    list_display = ("original_name", "owner", "target_type", "target_id", "size", "created_at")
    list_filter = ("target_type", "created_at")
    search_fields = ("original_name", "owner__username", "token")
