"""Demande de service du client (spec 003, ADR 0010).

La demande a son propre cycle de vie ; la réservation (``bookings``) naît quand le client
accepte un devis. Repère, position et description sont des données personnelles : jamais dans un
log, un audit ou une URL, et vidés à la purge ou à la suppression du compte.
"""

from django.conf import settings
from django.contrib.gis.db import models
from django.db.models import Q

from jeflink.common.models import BaseModel

LANDMARK_MAX_LENGTH = 300
DESCRIPTION_MAX_LENGTH = 1000


class ServiceRequest(BaseModel):
    class Status(models.TextChoices):
        NEEDS_ZONE = "needs_zone", "Quartier à vérifier"
        OPEN = "open", "Ouverte"
        QUOTED = "quoted", "Devis reçus"
        BOOKED = "booked", "Réservée"
        EXPIRED = "expired", "Expirée"
        CANCELLED = "cancelled", "Annulée"

    class When(models.TextChoices):
        ASAP = "asap", "Dès que possible"
        DATE = "date", "Un jour précis"

    class Period(models.TextChoices):
        MORNING = "morning", "Matin"
        AFTERNOON = "afternoon", "Après-midi"
        EVENING = "evening", "Soir"
        ANY = "any", "Peu importe"

    class Channel(models.TextChoices):
        WEB = "web", "Web"
        APP = "app", "App"
        WHATSAPP = "whatsapp", "WhatsApp"

    # Statuts où la demande vit encore (comptés dans la limite du client).
    LIVE = (Status.NEEDS_ZONE, Status.OPEN, Status.QUOTED, Status.BOOKED)

    client = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="service_requests"
    )
    trade = models.ForeignKey("catalog.Trade", on_delete=models.PROTECT, related_name="+")
    service = models.ForeignKey(
        "catalog.Service", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    # Nulle seulement en ``needs_zone`` (ou annulée avant d'être rattachée).
    zone = models.ForeignKey(
        "zones.Zone", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    # Quartier saisi en texte libre, normalisé et sans chiffres, en ``needs_zone`` seulement.
    zone_text = models.CharField(max_length=40, blank=True)
    landmark = models.CharField(max_length=LANDMARK_MAX_LENGTH, blank=True)
    location = models.PointField(srid=4326, null=True, blank=True)
    description = models.CharField(max_length=DESCRIPTION_MAX_LENGTH, blank=True)
    urgent = models.BooleanField(default=False)
    preferred_when = models.CharField(max_length=4, choices=When.choices, default=When.ASAP)
    preferred_date = models.DateField(null=True, blank=True)
    preferred_period = models.CharField(max_length=9, choices=Period.choices, default=Period.ANY)
    status = models.CharField(max_length=10, choices=Status.choices)
    # Posé au passage en ``open`` : le temps passé en ``needs_zone`` ne compte pas.
    expires_at = models.DateTimeField(null=True, blank=True)
    channel = models.CharField(max_length=8, choices=Channel.choices)
    idempotency_key = models.CharField(max_length=64)
    payload_hash = models.CharField(max_length=64)
    # Ordre de diffusion aux pros (urgence puis ancienneté) : une seule clé triable, pour que la
    # pagination par curseur reste exacte. Fixée à la création, voir ``services.dispatch_rank``.
    dispatch_rank = models.BigIntegerField(default=0)
    first_quoted_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    close_reason = models.CharField(max_length=24, blank=True)
    # Pros qui se sont désistés de cette demande : elle ne leur est plus montrée.
    excluded_providers = models.ManyToManyField(
        "providers.Provider", blank=True, related_name="excluded_requests"
    )

    class Meta:
        verbose_name = "demande"
        ordering = ("-created_at",)
        permissions = [("attach_servicerequest", "Demandes : rattacher à une zone")]
        indexes = [
            models.Index(fields=("status", "expires_at")),
            models.Index(fields=("client", "status")),
            models.Index(fields=("status", "dispatch_rank")),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=("client", "idempotency_key"), name="request_idempotency_per_client"
            ),
            # Un repère ou une position, tant que la demande vit (vidés ensuite, RGPD).
            models.CheckConstraint(
                condition=~Q(status__in=("needs_zone", "open", "quoted", "booked"))
                | ~Q(landmark="")
                | Q(location__isnull=False),
                name="request_landmark_or_location",
            ),
            models.CheckConstraint(
                condition=Q(zone__isnull=False) | Q(status__in=("needs_zone", "cancelled")),
                name="request_zone_unless_needs_zone",
            ),
            models.CheckConstraint(
                condition=Q(preferred_when="asap") | Q(preferred_date__isnull=False),
                name="request_date_when_date",
            ),
        ]

    def __str__(self) -> str:
        return f"demande {self.status}"
