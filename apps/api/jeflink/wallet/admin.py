"""Grand livre dans l'admin Django (spec 005) : lecture seule, aucune suppression nulle part.
Une erreur se corrige par une contre-passation (actions de la tâche 6), jamais par une édition.
La note de l'Ops est visible ici seulement."""

from django.contrib import admin
from django.db.models import BigIntegerField, Case, F, QuerySet, Sum, When
from django.db.models.functions import Coalesce
from django.http import HttpRequest

from .models import CREDIT_NORMAL_KINDS, LedgerAccount, LedgerEntry, LedgerTransaction, Side


class ReadOnlyAdmin(admin.ModelAdmin):
    def has_add_permission(self, request: HttpRequest, obj=None) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj=None) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj=None) -> bool:
        return False


class LedgerEntryInline(admin.TabularInline):
    model = LedgerEntry
    fields = ("account", "side", "amount_xof")
    readonly_fields = fields
    extra = 0
    can_delete = False

    def has_add_permission(self, request: HttpRequest, obj=None) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj=None) -> bool:
        return False


@admin.register(LedgerTransaction)
class LedgerTransactionAdmin(ReadOnlyAdmin):
    list_display = ("created_at", "kind", "provider", "reason_code", "actor_kind")
    list_filter = ("kind", "actor_kind", "reason_code")
    readonly_fields = (
        "public_id", "kind", "idempotency_key", "provider", "booking", "reverses", "reason_code",
        "note", "actor", "actor_kind", "created_at",
    )  # fmt: skip
    fields = readonly_fields
    inlines = (LedgerEntryInline,)

    def get_queryset(self, request: HttpRequest) -> QuerySet[LedgerTransaction]:
        return super().get_queryset(request).select_related("provider")


@admin.register(LedgerAccount)
class LedgerAccountAdmin(ReadOnlyAdmin):
    list_display = ("kind", "provider", "balance_xof", "last_reminder_at")
    list_filter = ("kind",)
    readonly_fields = ("kind", "provider", "last_reminder_at", "created_at")
    fields = readonly_fields

    def get_queryset(self, request: HttpRequest) -> QuerySet[LedgerAccount]:
        signed = Case(
            When(entries__side=Side.DEBIT, then=F("entries__amount_xof")),
            default=-F("entries__amount_xof"),
            output_field=BigIntegerField(),
        )
        return (
            super()
            .get_queryset(request)
            .select_related("provider")
            .annotate(net_xof=Coalesce(Sum(signed), 0))
        )

    @admin.display(description="Solde (F CFA)")
    def balance_xof(self, account: LedgerAccount) -> int:
        return -account.net_xof if account.kind in CREDIT_NORMAL_KINDS else account.net_xof
