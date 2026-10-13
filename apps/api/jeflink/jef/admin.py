from django.contrib import admin

from .models import JefSession


@admin.register(JefSession)
class JefSessionAdmin(admin.ModelAdmin):
    """Lecture seule : les échanges se consultent aussi dans la console (rubrique Jef)."""

    list_display = ["id", "client", "trade", "mode", "request", "created_at"]
    list_filter = ["mode", "trade"]
    readonly_fields = [f.name for f in JefSession._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
