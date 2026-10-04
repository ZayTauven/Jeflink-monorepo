"""Demandes non servies : lecture seule pour l'Ops (où recruter, quel métier ouvrir)."""

from django.contrib import admin
from django.http import HttpRequest

from .models import UnservedDemand


@admin.register(UnservedDemand)
class UnservedDemandAdmin(admin.ModelAdmin):
    list_display = ("occurred_at", "reason", "trade_slug", "zone_slug", "zone_text", "channel")
    list_filter = ("reason", "channel", "trade_slug")
    date_hierarchy = "occurred_at"

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj=None) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj=None) -> bool:
        return False
