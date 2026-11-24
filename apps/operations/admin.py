from django.contrib import admin

from .models import AccountAuditLog


@admin.register(AccountAuditLog)
class AccountAuditLogAdmin(admin.ModelAdmin):
    list_display = (
        "created_at",
        "action",
        "actor",
        "target_user",
        "summary",
        "ip_address",
    )
    list_filter = ("action", "created_at")
    search_fields = (
        "actor__username",
        "actor__display_name",
        "target_user__username",
        "target_user__display_name",
        "summary",
    )
    readonly_fields = (
        "actor",
        "target_user",
        "action",
        "summary",
        "metadata",
        "ip_address",
        "created_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
