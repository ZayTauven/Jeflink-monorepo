"""Villes et zones (quartiers ou communes), spec 002 : des données saisies par l'Ops.

Une zone est un centre et un rayon ; un ``boundary`` saisi prime sur le cercle.
"""

from django.contrib.gis.db import models
from django.db.models import Q

from jeflink.catalog.models import aliases_field
from jeflink.common.models import BaseModel
from jeflink.common.slugs import slug_check, validate_reference_slug

RADIUS_MIN_M = 200
RADIUS_MAX_M = 15_000


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
    name = models.CharField("nom", max_length=80)
    # Unique partout : l'URL /[metier]/[quartier] ne porte pas la ville.
    slug = models.CharField(
        max_length=50,
        unique=True,
        validators=[validate_reference_slug],
        help_text="Identifiant de l'URL (/plombier/ouakam). Figé après création.",
    )
    aliases = aliases_field()
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
