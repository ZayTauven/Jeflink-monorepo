from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from jeflink.accounts.models import PHONE_E164_SN


class AuditLog(models.Model):
    """Journal des actions de l'équipe dans la console : qui a fait quoi, sur quoi, quand."""

    class Action(models.TextChoices):
        PRO_VERIFY = "pro.verify", "Pro vérifié"
        PRO_REJECT = "pro.reject", "Vérification refusée"
        USER_SUSPEND = "user.suspend", "Compte suspendu"
        USER_REACTIVATE = "user.reactivate", "Compte réactivé"
        REQUEST_CANCEL = "request.cancel", "Demande annulée par l'équipe"
        REQUEST_NOTE = "request.note", "Note interne modifiée"
        REVIEW_HIDE = "review.hide", "Avis masqué"
        REVIEW_SHOW = "review.show", "Avis rétabli"
        CONTACT_HANDLE = "contact.handle", "Message traité"
        CONTACT_REOPEN = "contact.reopen", "Message rouvert"
        DISPUTE_OPEN = "dispute.open", "Litige ouvert"
        DISPUTE_UPDATE = "dispute.update", "Litige mis à jour"
        TRADE_CREATE = "trade.create", "Métier créé"
        TRADE_UPDATE = "trade.update", "Métier modifié"
        ZONE_CREATE = "zone.create", "Quartier ajouté"
        ZONE_UPDATE = "zone.update", "Quartier modifié"
        SETTINGS_UPDATE = "settings.update", "Réglages modifiés"
        TEAM_ADD = "team.add", "Membre de l'équipe ajouté"
        TEAM_ROLE = "team.role", "Rôle modifié"
        TEAM_DEACTIVATE = "team.deactivate", "Accès à la console retiré"
        TEAM_REACTIVATE = "team.reactivate", "Accès à la console rétabli"
        COUPON_CREATE = "coupon.create", "Code promo créé"
        COUPON_UPDATE = "coupon.update", "Code promo modifié"
        CAMPAIGN_CREATE = "campaign.create", "Campagne créée"
        CAMPAIGN_UPDATE = "campaign.update", "Campagne modifiée"
        COMMISSION_UPDATE = "commission.update", "Commission modifiée"
        SETTLEMENT_ADD = "settlement.add", "Règlement enregistré"

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+"
    )
    action = models.CharField(max_length=30, choices=Action.choices)
    target_type = models.CharField("type de cible", max_length=20)
    target_id = models.PositiveIntegerField()
    target_label = models.CharField("cible", max_length=200)
    details = models.CharField("précisions", max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        verbose_name = "action de l'équipe"
        verbose_name_plural = "journal d'audit"

    def __str__(self):
        return f"{self.get_action_display()} — {self.target_label}"


class PlatformSettings(models.Model):
    """Réglages de la plateforme (une seule ligne), modifiés par un super admin dans la console."""

    max_quotes = models.PositiveSmallIntegerField(
        "devis maximum par demande",
        default=3,
        validators=[MinValueValidator(1), MaxValueValidator(10)],
        help_text="Au-delà, la demande ne reçoit plus de devis : évite la course au moins-disant.",
    )
    stale_after_hours = models.PositiveSmallIntegerField(
        "alerte « sans devis » après (heures)",
        default=24,
        validators=[MinValueValidator(1), MaxValueValidator(168)],
    )
    accepting_requests = models.BooleanField(
        "nouvelles demandes ouvertes",
        default=True,
        help_text="Décocher pour mettre les nouvelles demandes en pause (fête, saturation…).",
    )
    closed_message = models.CharField(
        "message quand les demandes sont en pause", max_length=200, blank=True
    )
    support_whatsapp = models.CharField(
        "WhatsApp du support", max_length=13, blank=True, validators=[PHONE_E164_SN]
    )
    support_email = models.EmailField("email du support", blank=True)
    default_commission_percent = models.PositiveSmallIntegerField(
        "commission par défaut (%)",
        default=10,
        validators=[MaxValueValidator(50)],
        help_text="Prélevée sur le devis accepté ; un métier peut avoir son propre taux.",
    )
    jef_enabled = models.BooleanField(
        "Jef proposé aux clients",
        default=True,
        help_text="L'assistant qui aide à décrire le souci avant de publier une demande.",
    )
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    class Meta:
        verbose_name = "réglages de la plateforme"
        verbose_name_plural = "réglages de la plateforme"

    def __str__(self):
        return "Réglages de la plateforme"

    @classmethod
    def load(cls) -> "PlatformSettings":
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class ProSettlement(models.Model):
    """Règlement entre un pro et Jeflink (commission versée, remise reversée…), saisi en Finance."""

    class Direction(models.TextChoices):
        TO_JEFLINK = "to_jeflink", "Le pro a payé Jeflink"
        TO_PRO = "to_pro", "Jeflink a payé le pro"

    class Method(models.TextChoices):
        CASH = "cash", "Espèces"
        WAVE = "wave", "Wave"
        ORANGE_MONEY = "orange_money", "Orange Money"
        TRANSFER = "transfer", "Virement"

    pro = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="settlements"
    )
    direction = models.CharField("sens", max_length=12, choices=Direction.choices)
    amount = models.PositiveIntegerField("montant (F CFA)", validators=[MinValueValidator(1)])
    method = models.CharField("moyen", max_length=14, choices=Method.choices)
    reference = models.CharField("référence", max_length=60, blank=True)
    note = models.CharField(max_length=200, blank=True)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "règlement d'un pro"
        verbose_name_plural = "règlements des pros"

    def __str__(self):
        return f"{self.get_direction_display()} — {self.amount} F CFA"

    @property
    def signed(self) -> int:
        """Effet sur le solde dû par le pro : un paiement du pro le réduit."""
        return -self.amount if self.direction == self.Direction.TO_JEFLINK else self.amount
