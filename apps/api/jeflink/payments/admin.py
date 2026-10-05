"""Paiements dans l'admin Django (spec 005).

- Canaux : saisis par la Comptabilité, jamais supprimés.
- Règlements : le groupe « Rapprochement » confirme, renvoie à corriger ou rejette une
  déclaration, et saisit un versement vu dans le relevé ou des espèces remises au bureau. Chaque
  écriture exige un code TOTP saisi depuis moins de 5 minutes (``StepUpForm``) ; un opérateur
  n'agit jamais sur son propre compte pro (service).
- La référence de transaction n'est visible que dans l'admin, jamais dans une URL : pas de
  recherche par référence.
"""

import uuid

from django import forms
from django.contrib import admin, messages
from django.contrib.admin.helpers import ACTION_CHECKBOX_NAME
from django.core.exceptions import PermissionDenied
from django.db.models import QuerySet
from django.http import HttpRequest, HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import path, reverse

from jeflink.accounts.admin_site import StepUpForm
from jeflink.common.errors import DomainError
from jeflink.providers.models import Provider

from . import services
from .models import Gateway, PaymentIntent, SettlementChannel

ERRORS = {
    "operator_is_provider": "Vous ne pouvez pas décider pour votre propre compte pro.",
    "settlement_not_pending": "Ce règlement n'attend plus de décision.",
    "settlement_not_correctable": "Ce règlement a déjà été renvoyé une fois au pro.",
    "settlement_reference_used": "Cette référence a déjà servi sur ce canal.",
    "settlement_reference_invalid": "Référence invalide (6 à 40 lettres ou chiffres).",
    "settlement_amount_invalid": "Montant invalide.",
    "paid_at_invalid": "Heure du paiement invalide (ni future, ni de plus de 30 jours).",
    "receipt_number_invalid": "Numéro de reçu invalide.",
    "channel_inactive": "Ce canal ne convient pas à ce type de règlement.",
    "note_invalid": "Note de 200 caractères au plus, sans numéro de téléphone.",
    "idempotency_key_reused": "Ce formulaire a déjà servi pour un autre règlement : rechargez-le.",
}


def _error(exc: DomainError) -> str:
    return ERRORS.get(exc.code, exc.code)


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
        services.save_channel(channel=obj, operator=request.user)


# --- Décisions sur une déclaration -------------------------------------------------------------


class ConfirmForm(StepUpForm):
    received_xof = forms.IntegerField(
        label="Montant reçu (F CFA)",
        min_value=1,
        required=False,
        help_text="Vide : le montant déclaré. Un seul règlement sélectionné pour le changer.",
    )


class CorrectionForm(StepUpForm):
    reason = forms.ChoiceField(label="Motif", choices=PaymentIntent.CorrectionReason.choices)


class RejectForm(StepUpForm):
    reason = forms.ChoiceField(label="Motif", choices=PaymentIntent.RejectReason.choices)
    note = forms.CharField(label="Note (sans numéro)", max_length=200, required=False)


# --- Saisie par l'Ops --------------------------------------------------------------------------


class _RecordForm(StepUpForm):
    provider = forms.ModelChoiceField(
        label="Pro", queryset=Provider.objects.order_by("business_name")
    )
    amount_xof = forms.IntegerField(label="Montant reçu (F CFA)", min_value=1)
    idempotency_key = forms.CharField(widget=forms.HiddenInput())


class MobileMoneyRecordForm(_RecordForm):
    channel = forms.ModelChoiceField(
        label="Canal",
        queryset=SettlementChannel.objects.filter(gateway=Gateway.MANUAL_MOBILE_MONEY),
    )
    reference = forms.CharField(label="Référence de la transaction (relevé)", max_length=60)
    paid_at = forms.DateTimeField(label="Heure du versement (relevé)")


class CashRecordForm(_RecordForm):
    channel = forms.ModelChoiceField(
        label="Caisse", queryset=SettlementChannel.objects.filter(gateway=Gateway.CASH)
    )
    receipt_number = forms.CharField(label="Numéro du reçu remis au pro", max_length=40)


@admin.register(PaymentIntent)
class PaymentIntentAdmin(admin.ModelAdmin):
    list_display = (
        "created_at", "provider", "channel", "origin", "declared_xof", "received_xof", "status",
        "reference",
    )  # fmt: skip
    list_filter = ("status", "origin", "channel")
    readonly_fields = (
        "public_id", "purpose", "gateway", "channel", "provider", "origin", "status",
        "declared_xof", "received_xof", "reference", "paid_at", "payer_last4", "receipt_number",
        "declared_by", "correction_reason", "corrected_at", "reject_reason", "decision_note",
        "decided_by", "decided_at", "created_at",
    )  # fmt: skip
    fields = readonly_fields
    actions = ("confirm", "request_correction", "reject")

    def get_queryset(self, request: HttpRequest):
        return super().get_queryset(request).select_related("provider", "channel")

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj=None) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj=None) -> bool:
        return False

    def has_decide_permission(self, request: HttpRequest) -> bool:
        return request.user.has_perm("payments.decide_paymentintent")

    def get_actions(self, request: HttpRequest):
        return super().get_actions(request) if self.has_decide_permission(request) else {}

    # Actions : une page intermédiaire, puis le service pour chaque règlement sélectionné.

    def _decide(self, request, queryset, *, action, title, form_class, apply):
        selected = list(queryset.select_related("provider"))
        if "apply" in request.POST:
            form = form_class(request.POST, request=request)
            if form.is_valid():
                done = 0
                for intent in selected:
                    try:
                        apply(intent, form.cleaned_data, len(selected))
                        done += 1
                    except DomainError as exc:
                        self.message_user(
                            request, f"{intent.public_id} : {_error(exc)}", messages.WARNING
                        )
                self.message_user(request, f"{done} règlement(s) traité(s).", messages.SUCCESS)
                return HttpResponseRedirect(request.get_full_path())
        else:
            form = form_class(request=request)
        context = {
            **self.admin_site.each_context(request),
            "title": title,
            "form": form,
            "intents_selected": selected,
            "action": action,
            "action_checkbox_name": ACTION_CHECKBOX_NAME,
            "opts": self.model._meta,
        }
        return TemplateResponse(request, "admin/payments/decide.html", context)

    @admin.action(
        description="Confirmer (versement retrouvé dans le relevé)", permissions=("decide",)
    )
    def confirm(self, request: HttpRequest, queryset: QuerySet[PaymentIntent]):
        def apply(intent, data, count):
            received = data.get("received_xof")
            if received is not None and count != 1:
                raise DomainError("settlement_amount_invalid")
            services.confirm_settlement(
                intent=intent, operator=request.user, received_xof=received or intent.declared_xof
            )

        return self._decide(
            request, queryset, action="confirm", title="Confirmer des règlements",
            form_class=ConfirmForm, apply=apply,
        )  # fmt: skip

    @admin.action(description="Renvoyer au pro pour correction", permissions=("decide",))
    def request_correction(self, request: HttpRequest, queryset: QuerySet[PaymentIntent]):
        def apply(intent, data, count):
            services.request_correction(intent=intent, operator=request.user, reason=data["reason"])

        return self._decide(
            request, queryset, action="request_correction",
            title="Renvoyer des règlements au pro", form_class=CorrectionForm, apply=apply,
        )  # fmt: skip

    @admin.action(description="Rejeter", permissions=("decide",))
    def reject(self, request: HttpRequest, queryset: QuerySet[PaymentIntent]):
        def apply(intent, data, count):
            services.reject_settlement(
                intent=intent, operator=request.user, reason=data["reason"], note=data["note"]
            )

        return self._decide(
            request, queryset, action="reject", title="Rejeter des règlements",
            form_class=RejectForm, apply=apply,
        )  # fmt: skip

    # Saisie d'un règlement par l'Ops.

    def get_urls(self):
        view = self.admin_site.admin_view
        return [
            path(
                "record-mobile-money/",
                view(self.record_mobile_money_view),
                name="payments_paymentintent_record_mobile_money",
            ),
            path(
                "record-cash/",
                view(self.record_cash_view),
                name="payments_paymentintent_record_cash",
            ),
            *super().get_urls(),
        ]

    def changelist_view(self, request: HttpRequest, extra_context=None):
        extra = {"can_record": self.has_decide_permission(request), **(extra_context or {})}
        return super().changelist_view(request, extra_context=extra)

    def record_mobile_money_view(self, request: HttpRequest):
        def record(data):
            return services.record_mobile_money_settlement(
                provider=data["provider"],
                operator=request.user,
                channel=data["channel"],
                amount_xof=data["amount_xof"],
                reference=data["reference"],
                paid_at=data["paid_at"],
                idempotency_key=data["idempotency_key"],
            )

        return self._record(
            request, MobileMoneyRecordForm, record, "Créditer un versement vu dans le relevé"
        )

    def record_cash_view(self, request: HttpRequest):
        def record(data):
            return services.record_cash_settlement(
                provider=data["provider"],
                operator=request.user,
                channel=data["channel"],
                amount_xof=data["amount_xof"],
                receipt_number=data["receipt_number"],
                idempotency_key=data["idempotency_key"],
            )

        return self._record(request, CashRecordForm, record, "Enregistrer des espèces")

    def _record(self, request, form_class, record, title):
        if not self.has_decide_permission(request):
            raise PermissionDenied
        if request.method == "POST":
            form = form_class(request.POST, request=request)
            if form.is_valid():
                try:
                    created = record(form.cleaned_data)
                except DomainError as exc:
                    form.add_error(None, _error(exc))
                else:
                    self.message_user(
                        request,
                        "Règlement enregistré." if created.created else "Déjà enregistré.",
                        messages.SUCCESS,
                    )
                    return HttpResponseRedirect(reverse("admin:payments_paymentintent_changelist"))
        else:
            form = form_class(request=request, initial={"idempotency_key": uuid.uuid4().hex})
        context = {
            **self.admin_site.each_context(request),
            "title": title,
            "form": form,
            "opts": self.model._meta,
        }
        return TemplateResponse(request, "admin/payments/record.html", context)
