"""Mesures du produit. Aucun identifiant d'utilisateur ici : des signaux, pas des personnes."""

from django.db import models
from django.utils import timezone

from jeflink.common.models import BaseModel


class UnservedDemand(BaseModel):
    """Une demande qu'on n'a pas pu servir (IA7) : où, quel métier, pourquoi.

    Un slug vide veut dire « inconnu » (l'événement de la spec 002 le note ``null``).

    Schéma de la spec 002 : ni utilisateur, ni texte libre autre que le quartier normalisé et
    sans chiffres, ni point GPS (seulement la zone la plus proche et une distance au km).
    """

    class Channel(models.TextChoices):
        WEB = "web", "Web"
        APP = "app", "App"
        WHATSAPP = "whatsapp", "WhatsApp"

    trade_slug = models.CharField(max_length=50, blank=True)
    zone_slug = models.CharField(max_length=50, blank=True)
    reason = models.CharField(max_length=24)
    zone_text = models.CharField(max_length=40, blank=True)
    nearest_zone_slug = models.CharField(max_length=50, blank=True)
    distance_km = models.PositiveSmallIntegerField(null=True, blank=True)
    channel = models.CharField(max_length=8, choices=Channel.choices)
    occurred_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        verbose_name = "demande non servie"
        verbose_name_plural = "demandes non servies"
        ordering = ("-occurred_at",)

    def __str__(self) -> str:
        return f"{self.reason} · {self.trade_slug or '?'} · {self.zone_slug or '?'}"
