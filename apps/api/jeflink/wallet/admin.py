"""Grand livre dans l'admin Django (spec 005) : lecture seule, aucune suppression nulle part.
Une erreur se corrige par une contre-passation (actions de la tâche 6), jamais par une édition.
La note de l'Ops est visible ici seulement."""

from django import forms
from django.contrib import admin
from django.core.exceptions import ValidationError
from django.db.models import BigIntegerField, Case, F, QuerySet, Sum, When
from django.db.models.functions import Coalesce
from django.http import HttpRequest

from jeflink.accounts.admin_site import StepUpForm
from jeflink.common.errors import DomainError

from .models import (
    CREDIT_NORMAL_KINDS,
    Commission,
    CommissionRate,
    LedgerAccount,
    LedgerEntry,
    LedgerTransaction,
    Side,
)
from .services import add_rate, check_rate

RATE_ERRORS = {
    "rate_invalid": "Taux en points de base, de 0 à 5 000 (1 000 = 10 %).",
    "rate_cap_invalid": "Le plafond est un montant positif, ou vide pour aucun plafond.",
    "rate_valid_from_past": "La date d'effet ne peut pas être dans le passé.",
    "note_invalid": "Note de 200 caractères au plus, sans numéro de téléphone.",
    "rate_duplicate": "Un taux existe déjà pour ce métier à cette date d'effet.",
}


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


class CommissionRateForm(StepUpForm, forms.ModelForm):
    valid_from = forms.DateTimeField(
        label="En vigueur à partir de",
        required=False,
        help_text="Vide : tout de suite. Jamais dans le passé.",
    )

    class Meta:
        model = CommissionRate
        fields = ("trade", "rate_bps", "cap_xof", "valid_from", "note")
        help_texts = {
            "trade": "Vide : taux par défaut, pour les métiers sans taux propre.",
            "rate_bps": "1 000 = 10 %. Le taux en vigueur à l'envoi du devis s'applique.",
        }

    def clean(self):
        data = super().clean()
        if self.errors:
            return data
        try:
            check_rate(
                trade=data.get("trade"),
                rate_bps=data["rate_bps"],
                cap_xof=data.get("cap_xof"),
                valid_from=data.get("valid_from"),
                note=data.get("note", ""),
            )
        except DomainError as exc:
            raise ValidationError(RATE_ERRORS.get(exc.code, exc.code)) from exc
        return data


@admin.register(CommissionRate)
class CommissionRateAdmin(admin.ModelAdmin):
    """Taux en ajout seul : on ajoute un taux qui remplace l'ancien à sa date d'effet."""

    form = CommissionRateForm
    list_display = ("valid_from", "trade", "rate_bps", "cap_xof", "created_by")
    list_filter = ("trade",)

    def get_queryset(self, request: HttpRequest) -> QuerySet[CommissionRate]:
        return super().get_queryset(request).select_related("trade", "created_by")

    def has_change_permission(self, request: HttpRequest, obj=None) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj=None) -> bool:
        return False

    def get_form(self, request: HttpRequest, obj=None, **kwargs):
        # Le second facteur redemandé lit la session : la requête est portée par la classe.
        form = super().get_form(request, obj, **kwargs)
        return type(form.__name__, (form,), {"step_up_request": request})

    def save_model(self, request: HttpRequest, obj: CommissionRate, form, change: bool) -> None:
        rate = add_rate(
            trade=obj.trade,
            rate_bps=obj.rate_bps,
            cap_xof=obj.cap_xof,
            valid_from=form.cleaned_data.get("valid_from"),
            note=obj.note,
            operator=request.user,
        )
        # L'admin poursuit avec ``obj`` (journal, redirection) : il devient la ligne créée.
        obj.pk, obj.public_id, obj.valid_from = rate.pk, rate.public_id, rate.valid_from
        obj._state.adding = False


@admin.register(Commission)
class CommissionAdmin(ReadOnlyAdmin):
    """Commissions des réservations closes : filtres pour l'Ops (fins sans code, litiges tranchés
    pour le client, exemptions), à qui revient de passer un avoir le cas échéant."""

    list_display = (
        "created_at", "provider", "trade", "base_xof", "rate_bps", "amount_xof", "status",
        "completion_method", "close_reason",
    )  # fmt: skip
    list_filter = ("status", "exempt_reason", "completion_method", "close_reason")
    readonly_fields = (
        "public_id", "booking", "provider", "trade", "base_xof", "rate", "rate_bps", "cap_xof",
        "amount_xof", "status", "exempt_reason", "completion_method", "close_reason",
        "ledger_transaction", "created_at",
    )  # fmt: skip
    fields = readonly_fields

    def get_queryset(self, request: HttpRequest) -> QuerySet[Commission]:
        return super().get_queryset(request).select_related("provider", "trade")
