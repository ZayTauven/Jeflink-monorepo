"""Paiements dans l'admin Django (spec 005). Canaux : saisis par la Comptabilité, jamais
supprimés. Intentions : lecture seule ici (les décisions de l'Ops arrivent avec la tâche 5) ; la
référence de transaction n'est visible que dans l'admin."""

from django.contrib import admin
from django.http import HttpRequest

from .models import PaymentIntent, SettlementChannel
from .services import save_channel


@admin.register(SettlementChannel)
class SettlementChannelAdmin(admin.ModelAdmin):
    list_display = ("label_fr", "slug", "gateway", "account_display", "is_active", "position")
    list_filter = ("gateway", "is_active")
    fields = (
        "slug", "gateway", "label_fr", "label_wo", "account_display", "instructions_fr",
        "instructions_wo", "is_active", "position",
    )  # fmt: skip

    def get_readonly_fields(self, request: HttpRequest, obj=None):
        return ("slug", "gateway") if obj is not None else ()

    def has_delete_permission(self, request: HttpRequest, obj=None) -> bool:
        return False

    def save_model(self, request: HttpRequest, obj: SettlementChannel, form, change: bool) -> None:
        save_channel(channel=obj, operator=request.user)


@admin.register(PaymentIntent)
class PaymentIntentAdmin(admin.ModelAdmin):
    list_display = (
        "created_at", "provider", "channel", "origin", "declared_xof", "received_xof", "status",
    )  # fmt: skip
    list_filter = ("status", "origin", "channel")
    readonly_fields = (
        "public_id", "purpose", "gateway", "channel", "provider", "origin", "status",
        "declared_xof", "received_xof", "reference", "paid_at", "payer_last4", "receipt_number",
        "declared_by", "correction_reason", "corrected_at", "reject_reason", "decision_note",
        "decided_by", "decided_at", "created_at",
    )  # fmt: skip
    fields = readonly_fields

    def get_queryset(self, request: HttpRequest):
        return super().get_queryset(request).select_related("provider", "channel")

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj=None) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj=None) -> bool:
        return False
