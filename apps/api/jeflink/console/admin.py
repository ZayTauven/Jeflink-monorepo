from django.contrib import admin

from .models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    """Journal en lecture seule : on ne réécrit pas l'histoire."""

    list_display = ["created_at", "actor", "action", "target_label", "details"]
    list_filter = ["action", "target_type"]
    search_fields = ["target_label", "details", "actor__email"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
