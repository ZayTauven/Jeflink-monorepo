"""Métiers et services (spec 002) : des données saisies par l'Ops, jamais des ``choices``.

Libellés traduisibles en colonnes ``_fr`` (obligatoire) et ``_wo`` (vide permis), ADR 0009.
"""

from django.contrib.postgres.fields import ArrayField
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from jeflink.common.models import BaseModel
from jeflink.common.slugs import slug_check, validate_reference_slug

ALIAS_MAX_LENGTH = 40

# Premier segment des URL du site public : un métier ne peut pas prendre la place d'une page.
RESERVED_TRADE_SLUGS = frozenset(
    {
        "a-propos",
        "admin",
        "aide",
        "api",
        "blog",
        "compte",
        "conditions",
        "confidentialite",
        "connexion",
        "contact",
        "demande",
        "devenir-pro",
        "metiers",
        "pro",
        "quartiers",
        "recherche",
        "static",
        "zones",
    }
)


def aliases_field() -> ArrayField:
    """Mots des clients, sans langue (un terme wolof validé s'y ajoute par saisie)."""
    return ArrayField(
        models.CharField(max_length=ALIAS_MAX_LENGTH),
        default=list,
        blank=True,
        help_text="Séparés par des virgules : « frigoriste, clim ».",
    )


class Trade(BaseModel):
    """Métier : plomberie, électricité… Désactivé plutôt que supprimé."""

    slug = models.CharField(
        max_length=50,
        unique=True,
        validators=[validate_reference_slug],
        help_text="Identifiant de l'URL (/plombier/ouakam). Figé après création.",
    )
    name_fr = models.CharField("nom (fr)", max_length=60)
    name_wo = models.CharField("nom (wo)", max_length=60, blank=True)
    short_description_fr = models.CharField("description courte (fr)", max_length=160, blank=True)
    short_description_wo = models.CharField("description courte (wo)", max_length=160, blank=True)
    seo_title_fr = models.CharField(
        "titre SEO (fr)", max_length=70, blank=True, help_text="H1 et titre de page ; sinon le nom."
    )
    seo_title_wo = models.CharField("titre SEO (wo)", max_length=70, blank=True)
    aliases = aliases_field()
    icon_key = models.CharField("pictogramme", max_length=40, blank=True)
    is_active = models.BooleanField("actif", default=True)
    position = models.PositiveSmallIntegerField(default=100)

    class Meta:
        verbose_name = "métier"
        ordering = ("position", "name_fr")
        constraints = [
            models.CheckConstraint(condition=slug_check(), name="trade_slug_format"),
            models.CheckConstraint(condition=~Q(name_fr=""), name="trade_name_fr_required"),
        ]

    def __str__(self) -> str:
        return self.name_fr

    def clean(self) -> None:
        if self.slug in RESERVED_TRADE_SLUGS:
            raise ValidationError({"slug": ValidationError("slug réservé", code="slug_reserved")})


class Service(BaseModel):
    """Ce qu'on fait dans un métier (« débouchage »), avec un prix de départ indicatif."""

    trade = models.ForeignKey(Trade, on_delete=models.PROTECT, related_name="services")
    slug = models.CharField(max_length=50, validators=[validate_reference_slug])
    name_fr = models.CharField("nom (fr)", max_length=80)
    name_wo = models.CharField("nom (wo)", max_length=80, blank=True)
    aliases = aliases_field()
    # Entier XOF ; jamais une fourchette, jamais transmis à l'IA pour être restitué (spec 002).
    price_from_xof = models.PositiveBigIntegerField("à partir de (XOF)", null=True, blank=True)
    urgent = models.BooleanField(
        default=False, help_text="Fuite, panne de courant, frigo en panne."
    )
    is_active = models.BooleanField("actif", default=True)
    position = models.PositiveSmallIntegerField(default=100)

    class Meta:
        verbose_name = "service"
        ordering = ("position", "name_fr")
        constraints = [
            models.UniqueConstraint(fields=("trade", "slug"), name="service_slug_unique_per_trade"),
            models.CheckConstraint(condition=slug_check(), name="service_slug_format"),
            models.CheckConstraint(condition=~Q(name_fr=""), name="service_name_fr_required"),
        ]

    def __str__(self) -> str:
        return self.name_fr
