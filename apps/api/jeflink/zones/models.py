"""Villes et zones (quartiers ou communes), spec 002 : des données saisies par l'Ops.

Une zone est un centre et un rayon ; un ``boundary`` saisi prime sur le cercle.
"""

from django.contrib.gis.db import models
from django.core.exceptions import ValidationError
from django.db.models import Q

from jeflink.catalog.models import RESERVED_ZONE_SLUGS, SEO_INTRO_MAX_LENGTH, aliases_field
from jeflink.common.models import BaseModel
from jeflink.common.search import normalize
from jeflink.common.slugs import slug_check, validate_reference_slug
from jeflink.common.validators import validate_public_text

RADIUS_MIN_M = 200
RADIUS_MAX_M = 15_000
LOCATIVE_MAX_LENGTH = 90


class City(BaseModel):
    name = models.CharField("nom", max_length=80)
    slug = models.CharField(max_length=50, unique=True, validators=[validate_reference_slug])
    is_active = models.BooleanField("active", default=True)

    class Meta:
        verbose_name = "ville"
        ordering = ("name",)
        constraints = [models.CheckConstraint(condition=slug_check(), name="city_slug_format")]

    def __str__(self) -> str:
        return self.name


class Zone(BaseModel):
    """Quartier de Dakar ou commune de banlieue. Nom propre, sans traduction (ADR 0009)."""

    city = models.ForeignKey(City, on_delete=models.PROTECT, related_name="zones")
    name = models.CharField("nom", max_length=80, validators=[validate_public_text])
    # Unique partout : l'URL /[metier]/[quartier] ne porte pas la ville.
    slug = models.CharField(
        max_length=50,
        unique=True,
        validators=[validate_reference_slug],
        help_text="Identifiant de l'URL (/plombier/ouakam). Figé après création.",
    )
    aliases = aliases_field()
    # Forme grammaticale du nom après « à » : « à Ouakam », « aux Almadies » (données, pas du code).
    locative_fr = models.CharField(
        "locatif (fr)",
        max_length=LOCATIVE_MAX_LENGTH,
        blank=True,
        validators=[validate_public_text],
        help_text="« à Ouakam », « au Plateau », « aux Almadies » : doit contenir le nom.",
    )
    locative_wo = models.CharField(
        "locatif (wo)",
        max_length=LOCATIVE_MAX_LENGTH,
        blank=True,
        validators=[validate_public_text],
    )
    seo_intro_fr = models.CharField(
        "texte des pages du quartier (fr)",
        max_length=SEO_INTRO_MAX_LENGTH,
        blank=True,
        validators=[validate_public_text],
        help_text="Français parlé, repères connus. Publié tel quel : ni numéro, ni lien. "
        "Sans texte, les pages du quartier ne sont pas indexées.",
    )
    seo_intro_wo = models.CharField(
        "texte des pages du quartier (wo)",
        max_length=SEO_INTRO_MAX_LENGTH,
        blank=True,
        validators=[validate_public_text],
    )
    center = models.PointField("centre", srid=4326)
    radius_m = models.PositiveIntegerField("rayon (m)", default=1500)
    boundary = models.MultiPolygonField(
        "contour", srid=4326, null=True, blank=True, help_text="Optionnel ; prime sur le cercle."
    )
    trades = models.ManyToManyField(
        "catalog.Trade", blank=True, related_name="zones", verbose_name="métiers ouverts"
    )
    position = models.PositiveSmallIntegerField(default=100, help_text="Popularité : 1 en tête.")
    is_active = models.BooleanField("active", default=True)

    class Meta:
        verbose_name = "zone"
        ordering = ("position", "name")
        constraints = [
            models.CheckConstraint(condition=slug_check(), name="zone_slug_format"),
            models.CheckConstraint(condition=~Q(name=""), name="zone_name_required"),
            models.CheckConstraint(
                condition=Q(radius_m__gte=RADIUS_MIN_M, radius_m__lte=RADIUS_MAX_M),
                name="zone_radius_bounds",
            ),
        ]

    def __str__(self) -> str:
        return self.name

    def clean(self) -> None:
        if self.slug in RESERVED_ZONE_SLUGS:
            raise ValidationError({"slug": ValidationError("slug réservé", code="slug_reserved")})
        # Pas de « à Ouakam » sur la fiche de Ngor : le locatif reprend le nom de la zone.
        if (
            self.locative_fr
            and f" {normalize(self.name)} " not in f" {normalize(self.locative_fr)} "
        ):
            raise ValidationError(
                {
                    "locative_fr": ValidationError(
                        "Le locatif doit contenir le nom de la zone.", code="locative_name_missing"
                    )
                }
            )
