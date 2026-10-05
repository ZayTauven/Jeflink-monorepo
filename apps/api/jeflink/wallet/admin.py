"""Grand livre dans l'admin Django (spec 005) : lecture seule, aucune suppression nulle part.
Une erreur se corrige par une écriture de plus (avoir, geste, correction, contre-passation),
jamais par une édition. Ces écritures sont réservées à la Comptabilité (``adjust_ledger``) et
exigent un code TOTP frais. La note de l'Ops est visible ici seulement."""

import uuid

from django import forms
from django.contrib import admin
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import BigIntegerField, Case, F, QuerySet, Sum, When
from django.db.models.functions import Coalesce
from django.http import HttpRequest
from django.urls import path, reverse

from jeflink.accounts.admin_site import StepUpForm
from jeflink.common.admin_forms import action_page, form_page
from jeflink.common.errors import DomainError
from jeflink.providers.models import Provider

from .models import (
    CREDIT_NORMAL_KINDS,
    Commission,
    CommissionRate,
    LedgerAccount,
    LedgerEntry,
    LedgerTransaction,
    Side,
)
from .services import (
    ADJUSTMENT_REASONS,
    add_rate,
    check_rate,
    post_correction_debit,
    post_goodwill_credit,
    waive_commission,
)

RATE_ERRORS = {
    "rate_invalid": "Taux en points de base, de 0 à 5 000 (1 000 = 10 %).",
    "rate_cap_invalid": "Le plafond est un montant positif, ou vide pour aucun plafond.",
    "rate_valid_from_past": "La date d'effet ne peut pas être dans le passé.",
    "note_invalid": "Note de 200 caractères au plus, sans numéro de téléphone.",
    "rate_duplicate": "Un taux existe déjà pour ce métier à cette date d'effet.",
}
ADJUSTMENT_ERRORS = {
    "operator_is_provider": "Vous ne pouvez pas ajuster votre propre compte pro.",
    "adjustment_reason_invalid": "Motif invalide.",
    "adjustment_amount_invalid": "Montant invalide.",
    "adjustment_exceeds_remaining": "Montant supérieur à ce qui reste de la commission.",
    "adjustment_not_allowed": "Ajustement impossible sur cet élément.",
    "note_invalid": "Note obligatoire, 200 caractères au plus, sans numéro de téléphone.",
}
REASON_CHOICES = [(code, code) for code in ADJUSTMENT_REASONS]


def has_adjust_permission(request: HttpRequest) -> bool:
    return request.user.has_perm("wallet.adjust_ledger")


class AdjustmentForm(StepUpForm):
    """Motif et note obligatoires ; la clé masquée rend le formulaire rejouable sans doublon."""

    reason_code = forms.ChoiceField(label="Motif", choices=REASON_CHOICES)
    note = forms.CharField(label="Note (obligatoire, sans numéro)", max_length=200)
    key = forms.CharField(widget=forms.HiddenInput())

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.is_bound:
            self.initial.setdefault("key", uuid.uuid4().hex)


class WaiveForm(AdjustmentForm):
    amount_xof = forms.IntegerField(label="Montant de l'avoir (F CFA)", min_value=1)


class LedgerAdjustmentForm(AdjustmentForm):
    KINDS = [
        ("goodwill", "Geste commercial (la dette baisse)"),
        ("correction", "Correction en faveur de Jeflink (la dette augmente)"),
    ]

    kind = forms.ChoiceField(label="Type", choices=KINDS)
    provider = forms.ModelChoiceField(
        label="Pro", queryset=Provider.objects.order_by("business_name")
    )
    amount_xof = forms.IntegerField(label="Montant (F CFA)", min_value=1)
    booking = forms.UUIDField(
        label="Réservation concernée (identifiant, facultatif)", required=False
    )


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

    def get_urls(self):
        return [
            path(
                "adjust/",
                self.admin_site.admin_view(self.adjust_view),
                name="wallet_ledgertransaction_adjust",
            ),
            *super().get_urls(),
        ]

    def changelist_view(self, request: HttpRequest, extra_context=None):
        extra = {"can_adjust": has_adjust_permission(request), **(extra_context or {})}
        return super().changelist_view(request, extra_context=extra)

    def adjust_view(self, request: HttpRequest):
        from jeflink.bookings.models import Booking

        if not has_adjust_permission(request):
            raise PermissionDenied

        def submit(data) -> str:
            common = {
                "provider": data["provider"],
                "amount_xof": data["amount_xof"],
                "reason_code": data["reason_code"],
                "note": data["note"],
                "operator": request.user,
                "key": data["key"],
            }
            if data["kind"] == "goodwill":
                post_goodwill_credit(**common)
                return "Geste commercial enregistré."
            booking = None
            if data["booking"]:
                booking = Booking.objects.filter(public_id=data["booking"]).first()
                if booking is None:
                    raise DomainError("adjustment_not_allowed")
            post_correction_debit(booking=booking, **common)
            return "Correction enregistrée."

        return form_page(
            self,
            request,
            title="Ajustement du portefeuille d'un pro",
            intro="Toujours avec un motif et une note. Le pro est prévenu.",
            form_class=LedgerAdjustmentForm,
            initial={},
            submit=submit,
            success_url=reverse("admin:wallet_ledgertransaction_changelist"),
            labels=ADJUSTMENT_ERRORS,
        )


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
    actions = ("waive",)

    def get_queryset(self, request: HttpRequest) -> QuerySet[Commission]:
        return super().get_queryset(request).select_related("provider", "trade")

    def has_adjust_permission(self, request: HttpRequest) -> bool:
        return has_adjust_permission(request)

    @admin.action(description="Passer un avoir", permissions=("adjust",))
    def waive(self, request: HttpRequest, queryset: QuerySet[Commission]):
        def apply(commission, data):
            waive_commission(
                commission=commission,
                amount_xof=data["amount_xof"],
                reason_code=data["reason_code"],
                note=data["note"],
                operator=request.user,
                key=f"{data['key']}-{commission.pk}",
            )

        return action_page(
            self,
            request,
            list(queryset.select_related("provider", "ledger_transaction")),
            action="waive",
            title="Passer un avoir",
            intro="L'avoir ne dépasse jamais ce qui reste de la commission. Le pro est prévenu.",
            form_class=WaiveForm,
            apply=apply,
            labels=ADJUSTMENT_ERRORS,
        )
