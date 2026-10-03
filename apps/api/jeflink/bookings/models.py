"""Réservation (spec 003, ADR 0010) : naît à ``accepted`` quand le client accepte un devis.

Aucune écriture de ``status`` hors de ``bookings/services.py`` (test d'architecture) : toute
transition passe par ``transition()`` et laisse un ``BookingEvent`` immuable.
"""

from django.conf import settings
from django.db import models
from django.db.models import Q

from jeflink.common.models import BaseModel

NOTE_MAX_LENGTH = 200


class Booking(BaseModel):
    class Status(models.TextChoices):
        ACCEPTED = "accepted", "Acceptée, en attente du pro"
        SCHEDULED = "scheduled", "Planifiée"
        EN_ROUTE = "en_route", "Pro en route"
        ON_SITE = "on_site", "Pro sur place"
        IN_PROGRESS = "in_progress", "Intervention en cours"
        COMPLETED = "completed", "Terminée"
        DISPUTED = "disputed", "Contestée"
        CLOSED = "closed", "Clôturée"
        CANCELLED = "cancelled", "Annulée"

    class Actor(models.TextChoices):
        CLIENT = "client", "Client"
        PRO = "pro", "Pro"
        SYSTEM = "system", "Système"
        OPS = "ops", "Équipe Jeflink"

    # Engage encore les deux parties : bloque la suppression d'un compte (spec 004).
    ENGAGED = (
        Status.ACCEPTED,
        Status.SCHEDULED,
        Status.EN_ROUTE,
        Status.ON_SITE,
        Status.IN_PROGRESS,
        Status.COMPLETED,
        Status.DISPUTED,
    )
    # Peut encore être annulée (suspension du pro, désistement) : de accepted à on_site.
    CANCELLABLE = (Status.ACCEPTED, Status.SCHEDULED, Status.EN_ROUTE, Status.ON_SITE)

    # Une demande a plusieurs réservations dans le temps, mais une seule active.
    request = models.ForeignKey(
        "requests.ServiceRequest", on_delete=models.PROTECT, related_name="bookings"
    )
    quote = models.OneToOneField("requests.Quote", on_delete=models.PROTECT, related_name="booking")
    client = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="bookings"
    )
    provider = models.ForeignKey(
        "providers.Provider", on_delete=models.PROTECT, related_name="bookings"
    )
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.ACCEPTED)
    # Copie du devis : informatif, aucun paiement ni écriture de grand livre (étape 5).
    amount_xof = models.PositiveBigIntegerField()
    # Montant du devis, jamais modifié : ``amount_xof`` change par un avenant accepté (spec 004).
    original_amount_xof = models.PositiveBigIntegerField()
    slot_start = models.DateTimeField()
    slot_end = models.DateTimeField()
    confirm_deadline = models.DateTimeField()
    cancelled_by = models.CharField(max_length=6, choices=Actor.choices, blank=True)
    cancel_reason = models.CharField(max_length=24, blank=True)
    # Horodatages du déroulé (heure du serveur, UTC ; l'heure de l'appareil reste en métadonnée).
    en_route_at = models.DateTimeField(null=True, blank=True)
    on_site_at = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    # Fin de la fenêtre de contestation, posée à ``completed`` ; la clôture suit.
    dispute_deadline = models.DateTimeField(null=True, blank=True)
    dispute_reminder_sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "réservation"
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=("status", "confirm_deadline")),
            models.Index(fields=("client", "status")),
            models.Index(fields=("provider", "status")),
            models.Index(fields=("status", "dispute_deadline")),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=("request",),
                condition=~Q(status="cancelled"),
                name="booking_one_active_per_request",
            ),
            models.CheckConstraint(condition=Q(amount_xof__gt=0), name="booking_amount_positive"),
            models.CheckConstraint(
                condition=Q(original_amount_xof__gt=0), name="booking_original_amount_positive"
            ),
            models.CheckConstraint(
                condition=Q(slot_end__gt=models.F("slot_start")), name="booking_slot_ordered"
            ),
            models.CheckConstraint(
                condition=~Q(status="cancelled") | ~Q(cancelled_by=""),
                name="booking_cancelled_has_author",
            ),
        ]

    def __str__(self) -> str:
        return f"réservation {self.status}"


class BookingEventQuerySet(models.QuerySet):
    """Journal immuable : ni mise à jour ni suppression en masse. Seule exception, l'effacement
    des notes à la suppression d'un compte (``wipe_notes``)."""

    def update(self, **kwargs):
        raise PermissionError("BookingEvent est immuable.")

    def delete(self):
        raise PermissionError("BookingEvent est immuable.")

    def wipe_notes(self) -> int:
        return super().update(note="")


class BookingEvent(models.Model):
    """Une transition de réservation. ``from_status`` est vide à la création."""

    booking = models.ForeignKey(Booking, on_delete=models.PROTECT, related_name="events")
    from_status = models.CharField(max_length=12, blank=True)
    to_status = models.CharField(max_length=12)
    # Nul pour le système. L'id entier ne sort jamais de l'API.
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    actor_kind = models.CharField(max_length=6, choices=Booking.Actor.choices)
    reason = models.CharField(max_length=24, blank=True)
    # Note libre du motif « autre » : numéros refusés, jamais dans un log ni un audit.
    note = models.CharField(max_length=NOTE_MAX_LENGTH, blank=True)
    # Schéma fermé : ``late`` et ``reliability_weight`` seulement (voir ``services``).
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = BookingEventQuerySet.as_manager()

    class Meta:
        ordering = ("created_at", "id")
        indexes = [models.Index(fields=("booking", "created_at"))]

    def __str__(self) -> str:
        return f"{self.from_status or '∅'} → {self.to_status}"

    def save(self, *args, **kwargs) -> None:
        if not self._state.adding:
            raise PermissionError("BookingEvent est immuable.")
        kwargs["force_insert"] = True
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise PermissionError("BookingEvent est immuable.")
