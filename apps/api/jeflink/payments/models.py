"""Canaux de règlement et intentions de paiement (spec 005, ADR 0002 et 0012).

Un règlement de commission est une ``PaymentIntent`` ouverte par la passerelle de son canal ;
confirmée, elle devient une écriture du grand livre (``payments`` appelle ``wallet``, jamais
l'inverse). En V2, WiiPay confirmera la même intention par webhook.

``reference`` (référence de la transaction mobile money) et ``payer_last4`` ne sortent jamais
dans un log, un audit, une URL ni un message d'erreur.
"""

from django.conf import settings
from django.db import models
from django.db.models import Q

from jeflink.common.models import BaseModel
from jeflink.common.slugs import slug_check, validate_reference_slug


class Gateway(models.TextChoices):
    MANUAL_MOBILE_MONEY = "manual_mobile_money", "Mobile money (déclaré, rapproché par l'Ops)"
    CASH = "cash", "Espèces au bureau"
    FAKE = "fake", "Factice (local et test seulement)"


class SettlementChannel(BaseModel):
    """Canal de règlement (Wave, Orange Money, caisse…) : une donnée saisie par la Comptabilité,
    jamais une liste en dur. Désactivé plutôt que supprimé ; slug figé après création."""

    slug = models.CharField(max_length=40, unique=True, validators=[validate_reference_slug])
    gateway = models.CharField(max_length=24, choices=Gateway.choices)
    label_fr = models.CharField("libellé (fr)", max_length=60)
    label_wo = models.CharField("libellé (wo)", max_length=60, blank=True)
    # Numéro marchand ou nom du compte Jeflink : pas une donnée personnelle.
    account_display = models.CharField("compte Jeflink affiché", max_length=60, blank=True)
    instructions_fr = models.TextField("instructions (fr)", max_length=600, blank=True)
    instructions_wo = models.TextField("instructions (wo)", max_length=600, blank=True)
    is_active = models.BooleanField("actif", default=True)
    position = models.PositiveSmallIntegerField(default=0)

    class Meta:
        verbose_name = "canal de règlement"
        verbose_name_plural = "canaux de règlement"
        ordering = ("position", "slug")
        constraints = [models.CheckConstraint(condition=slug_check(), name="channel_slug_valid")]

    def __str__(self) -> str:
        return self.label_fr


class PaymentIntent(BaseModel):
    class Purpose(models.TextChoices):
        COMMISSION_SETTLEMENT = "commission_settlement", "Règlement de commission"

    class Origin(models.TextChoices):
        PRO_DECLARED = "pro_declared", "Déclaré par le pro"
        OPS_RECORDED = "ops_recorded", "Saisi par l'Ops"

    class Status(models.TextChoices):
        DECLARED = "declared", "À rapprocher"
        NEEDS_CORRECTION = "needs_correction", "À corriger par le pro"
        CONFIRMED = "confirmed", "Confirmé"
        REJECTED = "rejected", "Rejeté"
        CANCELLED = "cancelled", "Retiré par le pro"

    class CorrectionReason(models.TextChoices):
        REFERENCE_NOT_FOUND = "reference_not_found", "Référence introuvable"
        AMOUNT_MISMATCH = "amount_mismatch", "Montant différent"
        PAID_AT_MISMATCH = "paid_at_mismatch", "Heure différente"

    class RejectReason(models.TextChoices):
        NOT_FOUND = "not_found", "Introuvable dans le relevé"
        AMOUNT_MISMATCH = "amount_mismatch", "Montant différent"
        DUPLICATE = "duplicate", "Déjà déclaré"
        OTHER = "other", "Autre"

    # En attente de la décision de l'Ops.
    PENDING_STATUSES = (Status.DECLARED, Status.NEEDS_CORRECTION)
    # Une référence de ces statuts ne peut plus servir.
    CLOSED_WITHOUT_PAYMENT = (Status.REJECTED, Status.CANCELLED)

    purpose = models.CharField(max_length=24, choices=Purpose.choices)
    gateway = models.CharField(max_length=24, choices=Gateway.choices)
    channel = models.ForeignKey(SettlementChannel, on_delete=models.PROTECT, related_name="+")
    provider = models.ForeignKey(
        "providers.Provider", on_delete=models.PROTECT, related_name="payment_intents"
    )
    origin = models.CharField(max_length=12, choices=Origin.choices)
    status = models.CharField(max_length=16, choices=Status.choices)
    declared_xof = models.PositiveBigIntegerField()
    received_xof = models.PositiveBigIntegerField(null=True, blank=True)
    reference = models.CharField(max_length=40, blank=True)  # normalisée, majuscules
    paid_at = models.DateTimeField(null=True, blank=True)  # heure déclarée du paiement
    payer_last4 = models.CharField(max_length=4, blank=True)  # vide : payé du numéro du pro
    receipt_number = models.CharField(max_length=40, blank=True)  # espèces
    idempotency_key = models.CharField(max_length=80)
    payload_hash = models.CharField(max_length=64)
    declared_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    correction_reason = models.CharField(
        max_length=20, choices=CorrectionReason.choices, blank=True
    )
    corrected_at = models.DateTimeField(null=True, blank=True)
    reject_reason = models.CharField(max_length=16, choices=RejectReason.choices, blank=True)
    # Note de l'Ops (numéros refusés), jamais journalisée ni auditée.
    decision_note = models.CharField(max_length=200, blank=True)
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    decided_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "intention de paiement"
        verbose_name_plural = "intentions de paiement"
        ordering = ("created_at",)
        indexes = [
            models.Index(fields=("status", "created_at")),
            models.Index(fields=("provider", "status")),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=("provider", "idempotency_key"), name="intent_unique_idempotency_key"
            ),
            # Une même transaction ne règle jamais deux fois sur un canal.
            models.UniqueConstraint(
                fields=("channel", "reference"),
                condition=~Q(reference="") & ~Q(status__in=("rejected", "cancelled")),
                name="intent_unique_live_reference",
            ),
            models.CheckConstraint(
                condition=Q(declared_xof__gt=0), name="intent_declared_positive"
            ),
            models.CheckConstraint(
                condition=(
                    Q(status="confirmed") & Q(received_xof__gt=0) & Q(decided_at__isnull=False)
                )
                | (~Q(status="confirmed") & Q(received_xof__isnull=True)),
                name="intent_received_iff_confirmed",
            ),
            models.CheckConstraint(
                condition=(Q(status="rejected") & ~Q(reject_reason=""))
                | (~Q(status="rejected") & Q(reject_reason="")),
                name="intent_reject_reason_iff_rejected",
            ),
            models.CheckConstraint(
                condition=~Q(status="needs_correction") | ~Q(correction_reason=""),
                name="intent_correction_has_reason",
            ),
            models.CheckConstraint(
                condition=Q(payer_last4="") | Q(payer_last4__regex=r"^[0-9]{4}$"),
                name="intent_payer_last4_digits",
            ),
            models.CheckConstraint(
                condition=~Q(reference="") | ~Q(receipt_number=""),
                name="intent_reference_or_receipt",
            ),
        ]

    def __str__(self) -> str:
        return f"règlement {self.declared_xof} F ({self.status})"
