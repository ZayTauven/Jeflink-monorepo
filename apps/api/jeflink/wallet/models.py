"""Grand livre en partie double (spec 005, ADR 0012).

Une ``LedgerTransaction`` (l'en-tête) porte au moins deux ``LedgerEntry`` (les lignes), dont les
débits égalent les crédits. Montants en entiers XOF strictement positifs : le sens est porté par
``side``, jamais par un signe. Aucun solde stocké : il se calcule à la lecture
(``wallet.selectors``). Les deux tables sont immuables jusqu'en base (triggers) et l'équilibre est
vérifié au commit par un trigger de contrainte différé. Seul ``wallet.services.post_transaction``
écrit des lignes (test d'architecture).
"""

from django.conf import settings
from django.db import models
from django.db.models import Q

from jeflink.common.models import BaseModel


class AccountKind(models.TextChoices):
    PRO_COMMISSION_DUE = "pro_commission_due", "Commission due par le pro"
    PLATFORM_REVENUE = "platform_revenue", "Revenus de la plateforme"
    PLATFORM_COLLECTIONS = "platform_collections", "Fonds reçus, à rapprocher"
    PLATFORM_GOODWILL = "platform_goodwill", "Gestes commerciaux"
    # V2 (paiement en ligne) : déclarés, aucune écriture en V1 (refusés par post_transaction).
    CLIENT_ESCROW = "client_escrow", "Séquestre client (V2)"
    PRO_PENDING = "pro_pending", "Gains du pro en attente (V2)"
    PRO_AVAILABLE = "pro_available", "Gains du pro disponibles (V2)"


# Comptes qui appartiennent à un pro (les autres sont à la plateforme).
PROVIDER_ACCOUNT_KINDS = frozenset(
    {AccountKind.PRO_COMMISSION_DUE, AccountKind.PRO_PENDING, AccountKind.PRO_AVAILABLE}
)
V1_ACCOUNT_KINDS = frozenset(
    {
        AccountKind.PRO_COMMISSION_DUE,
        AccountKind.PLATFORM_REVENUE,
        AccountKind.PLATFORM_COLLECTIONS,
        AccountKind.PLATFORM_GOODWILL,
    }
)
# Sens normal : le solde d'un compte « débit » est ses débits moins ses crédits, l'inverse sinon.
CREDIT_NORMAL_KINDS = frozenset({AccountKind.PLATFORM_REVENUE})


def _iff(left: Q, right: Q) -> Q:
    """``left`` si et seulement si ``right``, en SQL."""
    return (left & right) | (~left & ~right)


class Side(models.TextChoices):
    DEBIT = "debit", "Débit"
    CREDIT = "credit", "Crédit"


class LedgerAccount(models.Model):
    """Compte du grand livre. Celui d'un pro naît à son premier mouvement ; ceux de la plateforme
    par migration (et à la demande, après un flush de test)."""

    kind = models.CharField(max_length=24, choices=AccountKind.choices)
    provider = models.ForeignKey(
        "providers.Provider",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="ledger_accounts",
    )
    # Canal de règlement d'un compte ``platform_collections`` (un compte par canal).
    channel = models.ForeignKey(
        "payments.SettlementChannel",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
    )
    # Dernière relance de dette envoyée au pro (spec 005, remind_debts). Seul champ modifiable.
    last_reminder_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "compte du grand livre"
        verbose_name_plural = "comptes du grand livre"
        constraints = [
            models.UniqueConstraint(
                fields=("kind", "provider", "channel"),
                name="ledgeraccount_unique_kind_provider_channel",
                nulls_distinct=False,
            ),
            models.CheckConstraint(
                condition=_iff(
                    Q(kind__in=sorted(PROVIDER_ACCOUNT_KINDS)), Q(provider__isnull=False)
                ),
                name="ledgeraccount_provider_iff_pro_kind",
            ),
            models.CheckConstraint(
                condition=_iff(Q(kind=AccountKind.PLATFORM_COLLECTIONS), Q(channel__isnull=False)),
                name="ledgeraccount_channel_iff_collections",
            ),
        ]

    def __str__(self) -> str:
        return self.kind if self.provider_id is None else f"{self.kind} · pro {self.provider_id}"


class TransactionKind(models.TextChoices):
    COMMISSION = "commission", "Commission"
    SETTLEMENT = "settlement", "Règlement"
    REVERSAL = "reversal", "Contre-passation"
    GOODWILL_CREDIT = "goodwill_credit", "Geste commercial"
    CORRECTION_DEBIT = "correction_debit", "Correction en faveur de Jeflink"


class ActorKind(models.TextChoices):
    SYSTEM = "system", "Système"
    OPS = "ops", "Ops"
    PRO = "pro", "Pro"


class LedgerTransaction(BaseModel):
    """En-tête d'un mouvement. Immuable : une erreur se corrige par une contre-passation."""

    kind = models.CharField(max_length=20, choices=TransactionKind.choices)
    idempotency_key = models.CharField(max_length=80, unique=True)
    provider = models.ForeignKey(
        "providers.Provider", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    booking = models.ForeignKey(
        "bookings.Booking", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    payment_intent = models.ForeignKey(
        "payments.PaymentIntent",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
    )
    reverses = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="reversals"
    )
    reason_code = models.CharField(max_length=24, blank=True)
    # Note de l'Ops (numéros refusés), jamais journalisée ni auditée.
    note = models.CharField(max_length=200, blank=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    actor_kind = models.CharField(max_length=8, choices=ActorKind.choices)

    class Meta:
        verbose_name = "transaction du grand livre"
        verbose_name_plural = "transactions du grand livre"
        ordering = ("-created_at",)
        permissions = [
            (
                "adjust_ledger",
                "Comptabilité : avoirs, gestes commerciaux, corrections et contre-passations",
            )
        ]
        constraints = [
            models.CheckConstraint(
                condition=_iff(Q(kind=TransactionKind.REVERSAL), Q(reverses__isnull=False)),
                name="ledgertransaction_reverses_iff_reversal",
            ),
            models.CheckConstraint(
                condition=Q(actor_kind=ActorKind.SYSTEM) | Q(actor__isnull=False),
                name="ledgertransaction_actor_unless_system",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.kind} {self.public_id}"


class LedgerEntry(models.Model):
    """Ligne d'une transaction. Immuable."""

    transaction = models.ForeignKey(
        LedgerTransaction, on_delete=models.PROTECT, related_name="entries"
    )
    account = models.ForeignKey(LedgerAccount, on_delete=models.PROTECT, related_name="entries")
    side = models.CharField(max_length=6, choices=Side.choices)
    amount_xof = models.PositiveBigIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "ligne du grand livre"
        verbose_name_plural = "lignes du grand livre"
        indexes = [models.Index(fields=("account", "created_at"))]
        constraints = [
            models.CheckConstraint(
                condition=Q(amount_xof__gt=0), name="ledgerentry_amount_positive"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.side} {self.amount_xof}"


RATE_BPS_MAX = 5_000  # 50 % : au-delà, c'est une erreur de saisie (points de base)


class CommissionRate(BaseModel):
    """Taux de commission, en ajout seul comme un journal (spec 005) : un nouveau taux remplace
    l'ancien à sa date d'effet. ``trade`` nul : taux par défaut. Le taux en vigueur à l'envoi du
    devis s'applique (ADR 0012). Immuable jusqu'en base."""

    trade = models.ForeignKey(
        "catalog.Trade", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    rate_bps = models.PositiveIntegerField("taux (points de base)")
    cap_xof = models.PositiveBigIntegerField("plafond par mission (F CFA)", null=True, blank=True)
    valid_from = models.DateTimeField("en vigueur à partir de")
    note = models.CharField(max_length=200, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )

    class Meta:
        verbose_name = "taux de commission"
        verbose_name_plural = "taux de commission"
        ordering = ("-valid_from",)
        constraints = [
            models.UniqueConstraint(
                fields=("trade", "valid_from"),
                name="commissionrate_unique_trade_valid_from",
                nulls_distinct=False,
            ),
            models.CheckConstraint(
                condition=Q(rate_bps__lte=RATE_BPS_MAX), name="commissionrate_rate_bps_max"
            ),
            models.CheckConstraint(
                condition=Q(cap_xof__isnull=True) | Q(cap_xof__gt=0),
                name="commissionrate_cap_positive",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.rate_bps} pb · {self.trade_id or 'défaut'} · {self.valid_from:%Y-%m-%d}"


class Commission(BaseModel):
    """Commission d'une réservation close (spec 005) : une par réservation, due ou exemptée, avec
    les copies de ce qui l'a fixée (assiette, taux, plafond, fin, motif de clôture). Immuable ;
    un avoir passe par une contre-passation de sa transaction."""

    class Status(models.TextChoices):
        CHARGED = "charged", "Due"
        EXEMPT = "exempt", "Exemptée"

    class ExemptReason(models.TextChoices):
        REVIEW_ACCOUNT = "review_account", "Compte de revue des stores"
        ZERO_RATE = "zero_rate", "Taux de 0"
        ZERO_AMOUNT = "zero_amount", "Montant arrondi à 0"
        RATE_MISSING = "rate_missing", "Aucun taux applicable"

    booking = models.OneToOneField(
        "bookings.Booking", on_delete=models.PROTECT, related_name="commission"
    )
    provider = models.ForeignKey("providers.Provider", on_delete=models.PROTECT, related_name="+")
    trade = models.ForeignKey("catalog.Trade", on_delete=models.PROTECT, related_name="+")
    base_xof = models.PositiveBigIntegerField()
    rate = models.ForeignKey(
        CommissionRate, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    rate_bps = models.PositiveIntegerField(null=True, blank=True)
    cap_xof = models.PositiveBigIntegerField(null=True, blank=True)
    amount_xof = models.PositiveBigIntegerField()
    status = models.CharField(max_length=8, choices=Status.choices)
    exempt_reason = models.CharField(max_length=16, choices=ExemptReason.choices, blank=True)
    completion_method = models.CharField(max_length=7, blank=True)
    close_reason = models.CharField(max_length=24)
    ledger_transaction = models.OneToOneField(
        LedgerTransaction, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )

    class Meta:
        verbose_name = "commission"
        ordering = ("-created_at",)
        indexes = [models.Index(fields=("provider", "created_at"))]
        constraints = [
            models.CheckConstraint(
                condition=_iff(
                    Q(status="charged"),
                    Q(amount_xof__gt=0) & Q(ledger_transaction__isnull=False),
                ),
                name="commission_charged_iff_posted",
            ),
            models.CheckConstraint(
                condition=_iff(Q(status="exempt"), ~Q(exempt_reason="")),
                name="commission_exempt_has_reason",
            ),
        ]

    def __str__(self) -> str:
        return f"commission {self.amount_xof} F ({self.status})"
