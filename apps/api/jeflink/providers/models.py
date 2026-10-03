"""Fiche pro minimale (spec 003) : qui peut deviser, où, et dans quel état de vérification.

Le vrai KYC viendra avec ``trust`` ; ici, la vérification est un statut posé par l'Ops.
"""

from django.conf import settings
from django.db import models
from django.db.models import Q

from jeflink.common.models import BaseModel

BUSINESS_NAME_MAX_LENGTH = 60


class Provider(BaseModel):
    class Status(models.TextChoices):
        PENDING = "pending", "En attente"
        VERIFIED = "verified", "Vérifié"
        SUSPENDED = "suspended", "Suspendu"

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="providers"
    )
    business_name = models.CharField("nom commercial", max_length=BUSINESS_NAME_MAX_LENGTH)
    trades = models.ManyToManyField("catalog.Trade", related_name="providers", blank=True)
    zones = models.ManyToManyField("zones.Zone", related_name="providers", blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    status_changed_at = models.DateTimeField(null=True, blank=True)
    # Numéros masqués dans ses messages de devis : un compteur, jamais le texte (spec 003).
    masked_numbers_count = models.PositiveIntegerField("numéros masqués", default=0)
    # Pro fictif des commandes de démo ; interdit hors local/test (contrôle au démarrage).
    is_demo = models.BooleanField("démo", default=False)

    class Meta:
        verbose_name = "pro"
        ordering = ("-created_at",)
        permissions = [("verify_provider", "Pros : vérifier ou suspendre une fiche")]
        constraints = [
            # Une seule fiche par gérant (l'équipe viendra avec les techniciens, étape 4).
            models.UniqueConstraint(fields=("owner",), name="provider_one_per_owner"),
            models.CheckConstraint(
                condition=~Q(business_name=""), name="provider_business_name_required"
            ),
        ]

    def __str__(self) -> str:
        return self.business_name
