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

    class CompletionMethod(models.TextChoices):
        CODE = "code", "Code de fin"
        NO_CODE = "no_code", "Sans code"

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
    # Fin de mission (spec 004). Le code est chiffré (MultiFernet), jamais renvoyé au pro, jamais
    # dans un log ni un audit ; effacé à ``completed`` ou ``cancelled``.
    completion_method = models.CharField(max_length=7, choices=CompletionMethod.choices, blank=True)
    no_code_reason = models.CharField(max_length=16, blank=True)
    completion_code_enc = models.TextField(blank=True)
    completion_code_attempts = models.PositiveSmallIntegerField(default=0)
    completion_code_locked = models.BooleanField(default=False)
    completion_code_regenerations = models.PositiveSmallIntegerField(default=0)
    completion_code_sms_sent = models.PositiveSmallIntegerField(default=0)
    # « Le pro est-il venu ? » envoyé au client (une seule fois), le créneau et la marge passés.
    no_show_check_sent_at = models.DateTimeField(null=True, blank=True)

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


class NoShowReport(BaseModel):
    """« Le pro n'est pas venu » déclaré par le client (spec 004).

    La réservation est annulée tout de suite et la demande rouverte, mais le poids de fiabilité du
    pro ne s'applique qu'à la confirmation : après 24 h sans contestation, ou sur décision de
    l'Ops. La note de contestation est un texte libre : jamais dans un log ni un audit.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "En attente de contestation"
        CONTESTED = "contested", "Contesté par le pro"
        CONFIRMED = "confirmed", "Confirmé"
        DISMISSED = "dismissed", "Écarté"

    booking = models.OneToOneField(Booking, on_delete=models.PROTECT, related_name="no_show")
    status = models.CharField(max_length=9, choices=Status.choices, default=Status.PENDING)
    contest_note = models.CharField(max_length=NOTE_MAX_LENGTH, blank=True)
    contested_at = models.DateTimeField(null=True, blank=True)
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    decided_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "no-show"
        ordering = ("-created_at",)
        permissions = [("decide_noshowreport", "Médiation : trancher un no-show")]
        indexes = [models.Index(fields=("status", "created_at"))]

    def __str__(self) -> str:
        return f"no-show {self.status}"


class BookingPhotoQuerySet(models.QuerySet):
    def visible(self):
        """Photos montrées au client et au pro : ni signalées, ni purgées, ni en échec."""
        return self.filter(hidden_at__isnull=True, purged_at__isnull=True).exclude(
            status=BookingPhoto.Status.FAILED
        )


class BookingPhoto(BaseModel):
    """Photo « avant » ou « après » d'une intervention (spec 004, ADR 0011).

    Seul le WebP réencodé sans métadonnée est stocké (jamais l'original ni son GPS). Les clés
    d'objet ne portent que des ``public_id``. Signalée par le client, une photo est masquée (le
    pro ne la voit plus) mais gardée pour l'Ops ; purgée 12 mois après la clôture.
    """

    class Phase(models.TextChoices):
        BEFORE = "before", "Avant"
        AFTER = "after", "Après"

    class Status(models.TextChoices):
        PROCESSING = "processing", "Miniature en cours"
        READY = "ready", "Prête"
        FAILED = "failed", "En échec"

    booking = models.ForeignKey(Booking, on_delete=models.PROTECT, related_name="photos")
    phase = models.CharField(max_length=6, choices=Phase.choices)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PROCESSING)
    image_key = models.CharField(max_length=120, blank=True)
    thumb_key = models.CharField(max_length=120, blank=True)
    width = models.PositiveIntegerField(default=0)
    height = models.PositiveIntegerField(default=0)
    size_bytes = models.PositiveIntegerField(default=0)
    # Heure déclarée par l'appareil, facultative : l'heure du serveur (``created_at``) fait foi.
    taken_at = models.DateTimeField(null=True, blank=True)
    idempotency_key = models.CharField(max_length=64)
    # Empreinte du fichier reçu et de sa phase : un rejeu avec un autre contenu est refusé.
    source_hash = models.CharField(max_length=64)
    hidden_at = models.DateTimeField(null=True, blank=True)
    hidden_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    purged_at = models.DateTimeField(null=True, blank=True)

    objects = BookingPhotoQuerySet.as_manager()

    class Meta:
        verbose_name = "photo"
        ordering = ("created_at", "id")
        indexes = [models.Index(fields=("booking", "phase"))]
        constraints = [
            models.UniqueConstraint(
                fields=("booking", "idempotency_key"), name="bookingphoto_idempotency"
            ),
        ]

    def __str__(self) -> str:
        return f"photo {self.phase} {self.status}"


class Amendment(BaseModel):
    """Avenant : le pro propose le **nouveau prix complet** pendant l'intervention ; seul le client
    le fait changer, depuis sa session (spec 004). Aucun mouvement d'argent : informatif."""

    class Status(models.TextChoices):
        PROPOSED = "proposed", "Proposé"
        ACCEPTED = "accepted", "Accepté"
        DECLINED = "declined", "Refusé"
        WITHDRAWN = "withdrawn", "Retiré"
        LAPSED = "lapsed", "Caduc"

    class Reason(models.TextChoices):
        VISIT_DIAGNOSIS = "visit_diagnosis", "Diagnostic sur place"
        EXTRA_WORK = "extra_work", "Travail en plus"
        PARTS = "parts", "Pièces"
        OTHER = "other", "Autre"

    booking = models.ForeignKey(Booking, on_delete=models.PROTECT, related_name="amendments")
    status = models.CharField(max_length=9, choices=Status.choices, default=Status.PROPOSED)
    reason = models.CharField(max_length=15, choices=Reason.choices)
    # Texte libre du pro (numéros refusés) : effacé à la suppression de son compte.
    note = models.CharField(max_length=NOTE_MAX_LENGTH, blank=True)
    previous_amount_xof = models.PositiveBigIntegerField()
    total_xof = models.PositiveBigIntegerField()
    idempotency_key = models.CharField(max_length=64)
    payload_hash = models.CharField(max_length=64)
    decided_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "avenant"
        ordering = ("created_at", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("booking", "idempotency_key"), name="amendment_idempotency"
            ),
            # Un seul avenant en attente à la fois, par réservation.
            models.UniqueConstraint(
                fields=("booking",),
                condition=Q(status="proposed"),
                name="amendment_one_proposed_per_booking",
            ),
            models.CheckConstraint(
                condition=Q(total_xof__gt=0) & Q(previous_amount_xof__gt=0),
                name="amendment_amounts_positive",
            ),
            models.CheckConstraint(
                condition=~Q(total_xof=models.F("previous_amount_xof")),
                name="amendment_changes_the_price",
            ),
        ]

    def __str__(self) -> str:
        return f"avenant {self.status}"


class AmendmentLine(models.Model):
    """Ligne d'un avenant (1 à 8), mêmes règles qu'une ligne de devis."""

    amendment = models.ForeignKey(Amendment, on_delete=models.CASCADE, related_name="lines")
    position = models.PositiveSmallIntegerField()
    kind = models.CharField(max_length=6)
    label = models.CharField(max_length=60, blank=True)
    amount_xof = models.PositiveBigIntegerField()

    class Meta:
        ordering = ("position",)
        constraints = [
            models.UniqueConstraint(
                fields=("amendment", "position"), name="amendmentline_position"
            ),
            models.CheckConstraint(
                condition=Q(amount_xof__gt=0), name="amendmentline_amount_positive"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.kind} {self.amount_xof}"


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
