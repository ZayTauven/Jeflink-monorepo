"""Sérialiseurs des réservations (spec 003) : une vue pour le client, une pour le pro.

Aucune logique métier. Le contact (numéro du pro, nom, numéro, repère et position du client) n'est
renvoyé qu'à partir de ``scheduled`` (``DISCLOSED_STATUSES``), jamais après une annulation.
"""

from typing import Any

from django.conf import settings
from django.utils import timezone
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from jeflink.bookings.machine import DISCLOSED_STATUSES, Actor
from jeflink.bookings.models import (
    Amendment,
    AmendmentLine,
    Booking,
    BookingPhoto,
    NoShowReport,
)
from jeflink.bookings.services import (
    CODE_STATUSES,
    can_report_no_show,
    change_pct,
    contest_deadline,
    no_show_available_at,
    photo_urls,
    requires_confirmation,
    visible_completion_code,
)
from jeflink.requests.api.refs import (
    ServiceRefSerializer,
    TradeRefSerializer,
    ZoneRefSerializer,
    masked,
)
from jeflink.reviews.api.serializers import (
    ClientReviewSerializer,
    ProReviewSerializer,
    RatingSerializer,
)
from jeflink.reviews.selectors import (
    can_review,
    published_review_for_provider,
    rating_for_providers,
    review_deadline,
)
from jeflink.trust.models import Dispute

# Étapes horodatées (UTC) et fin de la fenêtre de contestation : nulles tant qu'elles n'ont pas eu
# lieu. Mêmes champs pour le client et le pro.
TIMELINE_FIELDS = (
    "review",
    "dispute",
    "original_amount_xof",
    "amendments",
    "completion_method",
    "en_route_at",
    "on_site_at",
    "started_at",
    "completed_at",
    "closed_at",
    "dispute_deadline",
)


class AmendmentLineSerializer(serializers.ModelSerializer):
    class Meta:
        model = AmendmentLine
        fields = ["kind", "label", "amount_xof"]
        read_only_fields = fields


class AmendmentSerializer(serializers.ModelSerializer):
    """Un avenant : le nouveau prix complet, l'ancien, l'écart en % et les lignes.

    ``requires_confirmation`` : une hausse au-delà de ``AMENDMENT_CONFIRM_THRESHOLD_PCT`` demande
    une confirmation de plus au client ; une baisse, aucune. « Vous ne payez pas plus tant que
    vous n'avez pas accepté » : seul le client, depuis sa session, fait changer le montant.
    """

    lines = AmendmentLineSerializer(many=True)
    change_pct = serializers.SerializerMethodField()
    requires_confirmation = serializers.SerializerMethodField()

    class Meta:
        model = Amendment
        fields = [
            "public_id",
            "status",
            "reason",
            "note",
            "previous_amount_xof",
            "total_xof",
            "change_pct",
            "requires_confirmation",
            "lines",
            "created_at",
            "decided_at",
        ]
        read_only_fields = fields

    @extend_schema_field(serializers.IntegerField())
    def get_change_pct(self, amendment: Amendment) -> int:
        return change_pct(amendment)

    @extend_schema_field(serializers.BooleanField())
    def get_requires_confirmation(self, amendment: Amendment) -> bool:
        return requires_confirmation(amendment)


def booking_amendments(booking: Booking) -> list[dict]:
    return AmendmentSerializer(booking.amendments.all(), many=True).data


class DisputeStateSerializer(serializers.Serializer):
    """État du litige, sans le texte du client ni la note de l'Ops. ``decision`` est nulle tant
    que le litige est ouvert."""

    status = serializers.ChoiceField(choices=Dispute.Status.choices)
    reason = serializers.ChoiceField(choices=Dispute.Reason.choices)
    decision = serializers.ChoiceField(choices=Dispute.Decision.choices, allow_null=True)
    created_at = serializers.DateTimeField()
    resolved_at = serializers.DateTimeField(allow_null=True)


def dispute_state(booking: Booking) -> dict | None:
    dispute = getattr(booking, "dispute", None)
    if dispute is None:
        return None
    return {
        "status": dispute.status,
        "reason": dispute.reason,
        "decision": dispute.decision or None,
        "created_at": dispute.created_at,
        "resolved_at": dispute.resolved_at,
    }


class ReviewOwnerMixin:
    @extend_schema_field(ClientReviewSerializer(allow_null=True))
    def get_review(self, booking: Booking) -> dict | None:
        review = getattr(booking, "review", None)
        return ClientReviewSerializer(review).data if review is not None else None


class ReviewProMixin:
    @extend_schema_field(ProReviewSerializer(allow_null=True))
    def get_review(self, booking: Booking) -> dict | None:
        review = published_review_for_provider(booking)
        return ProReviewSerializer(review).data if review is not None else None


class AmendmentsMixin:
    """Les avenants de la réservation, du plus ancien au plus récent (client et pro)."""

    @extend_schema_field(AmendmentSerializer(many=True))
    def get_amendments(self, booking: Booking) -> list[dict]:
        return booking_amendments(booking)

    @extend_schema_field(DisputeStateSerializer(allow_null=True))
    def get_dispute(self, booking: Booking) -> dict | None:
        return dispute_state(booking)


class PhotoSerializer(serializers.ModelSerializer):
    """Une photo : miniature par défaut (environ 20 Ko), image pleine à la demande (1 600 px).

    Les deux URL sont signées et valables ``expires_at`` (10 min) : une page restée ouverte les
    renouvelle en rechargeant la réservation. Tant que la miniature se prépare, ``thumb_url``
    est l'image pleine.
    """

    thumb_url = serializers.SerializerMethodField()
    url = serializers.SerializerMethodField()
    expires_at = serializers.SerializerMethodField()

    class Meta:
        model = BookingPhoto
        fields = [
            "public_id",
            "phase",
            "status",
            "width",
            "height",
            "taken_at",
            "created_at",
            "thumb_url",
            "url",
            "expires_at",
        ]
        read_only_fields = fields

    def _urls(self, photo: BookingPhoto) -> dict:
        """Signées une seule fois par photo et par rendu (trois champs les lisent)."""
        cached = getattr(photo, "_signed", None)
        if cached is None:
            cached = photo._signed = photo_urls(photo)
        return cached

    @extend_schema_field(serializers.URLField())
    def get_thumb_url(self, photo: BookingPhoto) -> str:
        return self._urls(photo)["thumb_url"]

    @extend_schema_field(serializers.URLField())
    def get_url(self, photo: BookingPhoto) -> str:
        return self._urls(photo)["url"]

    @extend_schema_field(serializers.DateTimeField())
    def get_expires_at(self, photo: BookingPhoto) -> Any:
        return self._urls(photo)["expires_at"]


def booking_photos(booking: Booking) -> list[BookingPhoto]:
    """Photos visibles (préchargées par les sélecteurs, sinon une requête)."""
    loaded = getattr(booking, "visible_photos", None)
    if loaded is not None:
        return loaded
    return list(booking.photos.visible().order_by("created_at", "id"))


class NoShowStateSerializer(serializers.Serializer):
    """État d'un « le pro n'est pas venu ». Le pro voit en plus l'échéance de contestation."""

    status = serializers.ChoiceField(choices=NoShowReport.Status.choices)
    contest_deadline = serializers.DateTimeField(allow_null=True)
    can_contest = serializers.BooleanField()


def no_show_state(booking: Booking, *, for_pro: bool) -> dict | None:
    report = getattr(booking, "no_show", None)
    if report is None:
        return None
    pending = report.status == NoShowReport.Status.PENDING
    return {
        "status": report.status,
        "contest_deadline": contest_deadline(report) if for_pro and pending else None,
        "can_contest": for_pro and pending and timezone.now() <= contest_deadline(report),
    }


class ClientProviderSerializer(serializers.Serializer):
    """Le pro, tel que le client le voit avant la confirmation : nom commercial et badge."""

    business_name = serializers.CharField()
    verified = serializers.SerializerMethodField()
    rating = serializers.SerializerMethodField()

    def get_verified(self, provider) -> bool:
        return provider.status == "verified"

    @extend_schema_field(RatingSerializer(allow_null=True))
    def get_rating(self, provider) -> dict | None:
        """Note du pro (avis publiés), ``null`` sous 3 avis. Les vues la calculent une fois pour
        toute la page (``context["ratings"]``) ; sinon une requête."""
        ratings = self.context.get("ratings")
        if ratings is not None and provider.pk in ratings:
            return ratings[provider.pk]
        return rating_for_providers([provider.pk])[provider.pk]


class ClientContactSerializer(serializers.Serializer):
    """Le pro une fois la réservation planifiée : nom commercial et numéro (E.164)."""

    business_name = serializers.CharField()
    phone = serializers.CharField()


class ClientBookingSerializer(ReviewOwnerMixin, AmendmentsMixin, serializers.ModelSerializer):
    request = serializers.SlugRelatedField(slug_field="public_id", read_only=True)
    trade = TradeRefSerializer(source="request.trade")
    zone = ZoneRefSerializer(source="request.zone")
    provider = ClientProviderSerializer()
    quote = serializers.SlugRelatedField(slug_field="public_id", read_only=True)
    contact = serializers.SerializerMethodField()
    payment = serializers.SerializerMethodField()
    cancel_reason = serializers.SerializerMethodField()
    can_report_no_show = serializers.SerializerMethodField()
    can_dispute = serializers.SerializerMethodField()
    can_review = serializers.SerializerMethodField()
    review_deadline = serializers.SerializerMethodField()
    photos = serializers.SerializerMethodField()
    amendments = serializers.SerializerMethodField()
    dispute = serializers.SerializerMethodField()
    review = serializers.SerializerMethodField()
    completion_code = serializers.SerializerMethodField()
    can_regenerate_completion_code = serializers.SerializerMethodField()
    can_send_completion_code_sms = serializers.SerializerMethodField()
    no_show_available_at = serializers.SerializerMethodField()
    no_show = serializers.SerializerMethodField()

    class Meta:
        model = Booking
        fields = [
            "public_id",
            "request",
            "status",
            "trade",
            "zone",
            "provider",
            "quote",
            "amount_xof",
            "slot_start",
            "slot_end",
            "confirm_deadline",
            "contact",
            "payment",
            "can_report_no_show",
            "can_dispute",
            "can_review",
            "review_deadline",
            "photos",
            "completion_code",
            "completion_code_locked",
            "can_regenerate_completion_code",
            "can_send_completion_code_sms",
            "no_show_available_at",
            "no_show",
            *TIMELINE_FIELDS,
            "cancelled_by",
            "cancel_reason",
            "created_at",
        ]
        read_only_fields = fields

    @extend_schema_field(serializers.CharField())
    def get_cancel_reason(self, booking: Booking) -> str:
        """Message neutre : si le pro (ou le système) annule, le client ne voit jamais le motif
        (``too_far``, ``job_mismatch``…), seulement ``pro_withdrew``. Ses propres motifs restent."""
        if booking.cancelled_by in {Actor.PRO, Actor.SYSTEM}:
            return "pro_withdrew"
        return booking.cancel_reason

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_completion_code(self, booking: Booking) -> str | None:
        """Le code de fin, pour le client seul : à ne donner qu'à la fin, quand le travail lui
        convient. Jamais dans la vue du pro, un log ou un audit."""
        return visible_completion_code(booking)

    @extend_schema_field(serializers.BooleanField())
    def get_can_regenerate_completion_code(self, booking: Booking) -> bool:
        return (
            booking.status in CODE_STATUSES
            and booking.completion_code_regenerations < settings.COMPLETION_CODE_MAX_REGENERATIONS
        )

    @extend_schema_field(serializers.BooleanField())
    def get_can_send_completion_code_sms(self, booking: Booking) -> bool:
        limit = settings.COMPLETION_CODE_SMS_ON_DEMAND + (
            settings.COMPLETION_CODE_SMS_AUTO if booking.en_route_at else 0
        )
        return booking.status in CODE_STATUSES and booking.completion_code_sms_sent < limit

    @extend_schema_field(PhotoSerializer(many=True))
    def get_photos(self, booking: Booking) -> list[dict]:
        return PhotoSerializer(booking_photos(booking), many=True).data

    @extend_schema_field(serializers.BooleanField())
    def get_can_review(self, booking: Booking) -> bool:
        """Vrai de ``completed`` à ``review_deadline`` (14 jours, ou 7 jours après une décision de
        litige en faveur du client). L'avis est proposé, jamais exigé."""
        return can_review(booking)

    @extend_schema_field(serializers.DateTimeField(allow_null=True))
    def get_review_deadline(self, booking: Booking) -> Any:
        return review_deadline(booking)

    @extend_schema_field(serializers.BooleanField())
    def get_can_dispute(self, booking: Booking) -> bool:
        """Vrai de ``completed`` jusqu'à ``dispute_deadline`` ; l'heure limite est dans
        ``dispute_deadline`` (UTC), à afficher en heure de Dakar."""
        return (
            booking.status == "completed"
            and booking.dispute_deadline is not None
            and timezone.now() <= booking.dispute_deadline
        )

    @extend_schema_field(serializers.BooleanField())
    def get_can_report_no_show(self, booking: Booking) -> bool:
        return can_report_no_show(booking)

    @extend_schema_field(serializers.DateTimeField())
    def get_no_show_available_at(self, booking: Booking) -> Any:
        """Heure (UTC) dès laquelle « Il n'est pas venu » est permis : fin du créneau + marge."""
        return no_show_available_at(booking)

    @extend_schema_field(NoShowStateSerializer(allow_null=True))
    def get_no_show(self, booking: Booking) -> dict | None:
        return no_show_state(booking, for_pro=False)

    @extend_schema_field(ClientContactSerializer(allow_null=True))
    def get_contact(self, booking: Booking) -> dict[str, str] | None:
        """Le numéro du pro n'est partagé qu'à ``scheduled`` (et jamais après une annulation)."""
        if booking.status not in DISCLOSED_STATUSES:
            return None
        return {
            "business_name": booking.provider.business_name,
            "phone": booking.provider.owner.phone or "",
        }

    @extend_schema_field(serializers.CharField())
    def get_payment(self, booking: Booking) -> str:
        """Mention fixe : « À régler au pro, en espèces ou par mobile money. Jeflink ne garde
        aucun argent pour l'instant. » La phrase est une clé i18n côté front."""
        return "direct_to_pro"


class ProClientContactSerializer(serializers.Serializer):
    """Le client, une fois la réservation planifiée : nom et numéro (E.164)."""

    display_name = serializers.CharField()
    phone = serializers.CharField()


class LocationOutSerializer(serializers.Serializer):
    lat = serializers.FloatField()
    lon = serializers.FloatField()


class ProBookingSerializer(ReviewProMixin, AmendmentsMixin, serializers.ModelSerializer):
    """La réservation vue du pro. Avant ``scheduled`` : ni nom, ni numéro, ni repère, ni position
    du client, et les numéros de la description sont masqués."""

    request = serializers.SlugRelatedField(slug_field="public_id", read_only=True)
    trade = TradeRefSerializer(source="request.trade")
    service = ServiceRefSerializer(source="request.service", allow_null=True)
    zone = ZoneRefSerializer(source="request.zone")
    urgent = serializers.BooleanField(source="request.urgent")
    description = serializers.SerializerMethodField()
    client = serializers.SerializerMethodField()
    landmark = serializers.SerializerMethodField()
    location = serializers.SerializerMethodField()
    no_show = serializers.SerializerMethodField()
    photos = serializers.SerializerMethodField()
    amendments = serializers.SerializerMethodField()
    dispute = serializers.SerializerMethodField()
    review = serializers.SerializerMethodField()

    class Meta:
        model = Booking
        fields = [
            "public_id",
            "request",
            "status",
            "trade",
            "service",
            "zone",
            "urgent",
            "description",
            "amount_xof",
            "slot_start",
            "slot_end",
            "confirm_deadline",
            "client",
            "landmark",
            "location",
            "no_show",
            "photos",
            *TIMELINE_FIELDS,
            "cancelled_by",
            "cancel_reason",
            "created_at",
        ]
        read_only_fields = fields

    @extend_schema_field(NoShowStateSerializer(allow_null=True))
    def get_no_show(self, booking: Booking) -> dict | None:
        return no_show_state(booking, for_pro=True)

    @extend_schema_field(PhotoSerializer(many=True))
    def get_photos(self, booking: Booking) -> list[dict]:
        return PhotoSerializer(booking_photos(booking), many=True).data

    @staticmethod
    def _disclosed(booking: Booking) -> bool:
        return booking.status in DISCLOSED_STATUSES

    def get_description(self, booking: Booking) -> str:
        return masked(booking.request.description, disclosed=self._disclosed(booking))

    @extend_schema_field(ProClientContactSerializer(allow_null=True))
    def get_client(self, booking: Booking) -> dict[str, str] | None:
        if not self._disclosed(booking):
            return None
        return {"display_name": booking.client.display_name, "phone": booking.client.phone or ""}

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_landmark(self, booking: Booking) -> str | None:
        return booking.request.landmark if self._disclosed(booking) else None

    @extend_schema_field(LocationOutSerializer(allow_null=True))
    def get_location(self, booking: Booking) -> dict[str, Any] | None:
        point = booking.request.location
        if not self._disclosed(booking) or point is None:
            return None
        return {"lat": point.y, "lon": point.x}


# --- Entrées du pro ----------------------------------------------------------------------------


class OccurredAtSerializer(serializers.Serializer):
    """Heure de l'appareil (file hors ligne, étape 6) : métadonnée, le serveur fait foi."""

    occurred_at = serializers.DateTimeField(required=False, allow_null=True, default=None)


class StartSerializer(OccurredAtSerializer):
    # La file de l'appareil enverra les photos « avant » plus tard.
    photos_pending = serializers.BooleanField(required=False, default=False)


class ContestNoShowSerializer(serializers.Serializer):
    # Longueur et numéros vérifiés par le service (422 note_invalid).
    note = serializers.CharField(max_length=500, allow_blank=True)


class CompleteSerializer(OccurredAtSerializer):
    """Fin de mission : le code du client, ou un motif sans code. Le code vient dans le corps de
    la requête, jamais dans l'URL ; valeur vérifiée par le service."""

    code = serializers.CharField(max_length=12, required=False, allow_blank=True, default="")
    no_code_reason = serializers.CharField(
        max_length=24, required=False, allow_blank=True, default=""
    )
    photos_pending = serializers.BooleanField(required=False, default=False)


class PhotoUploadSerializer(serializers.Serializer):
    """Envoi multipart : la phase, le fichier (JPEG, PNG ou WebP, 8 Mo au plus) et, facultative,
    l'heure de la prise de vue. Le type est vérifié par décodage, jamais par l'extension."""

    phase = serializers.ChoiceField(choices=BookingPhoto.Phase.choices)
    file = serializers.FileField(allow_empty_file=False)
    taken_at = serializers.DateTimeField(required=False, allow_null=True, default=None)


class AmendmentLineInputSerializer(serializers.Serializer):
    # Valeurs vérifiées par le service (422 amendment_total_invalid).
    kind = serializers.CharField(max_length=6)
    amount_xof = serializers.IntegerField()
    label = serializers.CharField(max_length=60, required=False, allow_blank=True, default="")


class AmendmentProposeSerializer(serializers.Serializer):
    """Le nouveau prix **complet** (somme des lignes), avec un motif. Bornes et somme vérifiées par
    le service (422 amendment_total_invalid)."""

    reason = serializers.CharField(max_length=15)
    note = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")
    total_xof = serializers.IntegerField()
    lines = AmendmentLineInputSerializer(many=True)


class DisputeOpenSerializer(serializers.Serializer):
    """Motif de la liste fermée et texte de 10 à 1 000 caractères (vérifiés par le service)."""

    reason = serializers.CharField(max_length=12)
    description = serializers.CharField(max_length=2000, allow_blank=True)


class AmendmentAcceptSerializer(serializers.Serializer):
    """Le client accepte **ce qu'il a vu** : ``total_xof`` est le nouveau prix affiché
    (``409 amendment_total_mismatch`` s'il a changé). ``confirm`` doit être vrai quand
    ``requires_confirmation`` l'est (``422 amendment_confirmation_required``)."""

    total_xof = serializers.IntegerField()
    confirm = serializers.BooleanField(required=False, default=False)
