"""Vues des réservations (spec 003) : permissions, désérialisation, service, sérialisation.

Un objet d'un autre utilisateur répond 404. Une fiche pro suspendue lit encore ses réservations
(``HasOwnerRole`` + ``IsProOwner``) mais n'écrit plus (``IsVerifiedPro``).
"""

from django.conf import settings
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import generics, status
from rest_framework.parsers import MultiPartParser
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from jeflink.accounts.permissions import (
    HasOwnerRole,
    IsClient,
    IsProOwner,
    IsVerifiedPro,
    RequiresCompleteProfile,
)
from jeflink.bookings.machine import Actor
from jeflink.bookings.models import Booking
from jeflink.bookings.selectors import (
    amendment_for_client,
    amendment_for_provider,
    booking_for_client,
    booking_for_provider,
    bookings_for_client,
    bookings_for_provider,
)
from jeflink.bookings.services import (
    accept_amendment,
    cancel_booking,
    complete_work,
    confirm_booking,
    contest_no_show,
    create_from_quote,
    declare_no_show,
    decline_amendment,
    mark_arrived,
    mark_en_route,
    propose_amendment,
    regenerate_completion_code,
    report_photo,
    send_completion_code_sms,
    start_work,
    upload_photo,
    withdraw_amendment,
)
from jeflink.common.api.idempotency import IDEMPOTENCY_PARAMETER, idempotency_key
from jeflink.common.errors import DomainError
from jeflink.providers.models import Provider
from jeflink.providers.selectors import provider_for_owner
from jeflink.requests.api.serializers import ApiErrorSerializer, ReasonSerializer
from jeflink.requests.quotes import QuoteLineInput
from jeflink.requests.selectors import quote_for_client

from .serializers import (
    AmendmentProposeSerializer,
    AmendmentSerializer,
    ClientBookingSerializer,
    CompleteSerializer,
    ContestNoShowSerializer,
    OccurredAtSerializer,
    PhotoSerializer,
    PhotoUploadSerializer,
    ProBookingSerializer,
    StartSerializer,
)

ERRORS = {
    401: OpenApiResponse(description="not_authenticated"),
    403: OpenApiResponse(description="profile_incomplete, role_required, provider_not_verified"),
    404: OpenApiResponse(description="not_found"),
}


def error(description: str) -> OpenApiResponse:
    """Erreur métier : ``{"code": "..."}``, typée (``ApiError``) dans le client."""
    return OpenApiResponse(ApiErrorSerializer, description=description)


class AcceptQuoteView(APIView):
    """Le client accepte un devis : la réservation naît à ``accepted``."""

    permission_classes = [RequiresCompleteProfile]

    @extend_schema(
        tags=["bookings"],
        operation_id="quotes_accept",
        request=None,
        responses={
            201: ClientBookingSerializer,
            200: OpenApiResponse(ClientBookingSerializer, description="Rejeu : même réservation"),
            409: OpenApiResponse(
                description="quote_not_available (pris, expiré, retiré, créneau passé)"
            ),
            **ERRORS,
        },
    )
    def post(self, request: Request, public_id) -> Response:
        quote = quote_for_client(user=request.user, public_id=public_id)
        result = create_from_quote(quote=quote, actor=request.user)
        booking = booking_for_client(user=request.user, public_id=result.booking.public_id)
        code = status.HTTP_201_CREATED if result.created else status.HTTP_200_OK
        return Response(ClientBookingSerializer(booking).data, status=code)


class BookingListView(generics.ListAPIView):
    permission_classes = [IsClient]
    serializer_class = ClientBookingSerializer

    def get_queryset(self):
        return bookings_for_client(user=self.request.user)

    @extend_schema(
        tags=["bookings"],
        operation_id="bookings_list",
        responses={200: ClientBookingSerializer(many=True), **ERRORS},
    )
    def get(self, request: Request, *args, **kwargs) -> Response:
        return super().get(request, *args, **kwargs)


class BookingDetailView(APIView):
    permission_classes = [IsClient]

    @extend_schema(
        tags=["bookings"],
        operation_id="bookings_retrieve",
        responses={200: ClientBookingSerializer, **ERRORS},
    )
    def get(self, request: Request, public_id) -> Response:
        booking = booking_for_client(user=request.user, public_id=public_id)
        return Response(ClientBookingSerializer(booking).data)


class BookingCancelView(APIView):
    permission_classes = [IsClient]

    @extend_schema(
        tags=["bookings"],
        operation_id="bookings_cancel",
        request=ReasonSerializer,
        responses={
            200: ClientBookingSerializer,
            409: OpenApiResponse(description="transition_not_allowed"),
            422: OpenApiResponse(description="reason_invalid, note_invalid"),
            **ERRORS,
        },
    )
    def post(self, request: Request, public_id) -> Response:
        booking = booking_for_client(user=request.user, public_id=public_id)
        serializer = ReasonSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        cancel_booking(
            booking=booking, actor=request.user, actor_kind=Actor.CLIENT,
            **serializer.validated_data,
        )  # fmt: skip
        booking = booking_for_client(user=request.user, public_id=public_id)
        return Response(ClientBookingSerializer(booking).data)


class BookingNoShowView(APIView):
    permission_classes = [IsClient]

    @extend_schema(
        tags=["bookings"],
        operation_id="bookings_no_show",
        request=None,
        responses={
            200: ClientBookingSerializer,
            409: error("no_show_too_early, transition_not_allowed"),
            **ERRORS,
        },
    )
    def post(self, request: Request, public_id) -> Response:
        """« Le pro n'est pas venu » : après la fin du créneau plus une marge. Rejoué : 200."""
        booking = booking_for_client(user=request.user, public_id=public_id)
        declare_no_show(booking=booking, actor=request.user)
        booking = booking_for_client(user=request.user, public_id=public_id)
        return Response(ClientBookingSerializer(booking).data)


class BookingRegenerateCodeView(APIView):
    permission_classes = [IsClient]

    @extend_schema(
        tags=["bookings"],
        operation_id="bookings_completion_code_regenerate",
        request=None,
        responses={
            200: ClientBookingSerializer,
            409: error("completion_code_regen_limit, transition_not_allowed"),
            **ERRORS,
        },
    )
    def post(self, request: Request, public_id) -> Response:
        """Nouveau code de fin (3 fois au plus) : essais remis à zéro, code débloqué."""
        booking = booking_for_client(user=request.user, public_id=public_id)
        regenerate_completion_code(booking=booking, actor=request.user)
        booking = booking_for_client(user=request.user, public_id=public_id)
        return Response(ClientBookingSerializer(booking).data)


class BookingCodeSmsView(APIView):
    permission_classes = [IsClient]

    @extend_schema(
        tags=["bookings"],
        operation_id="bookings_completion_code_sms",
        request=None,
        responses={
            200: ClientBookingSerializer,
            409: error("transition_not_allowed"),
            429: error("sms_limit_reached"),
            **ERRORS,
        },
    )
    def post(self, request: Request, public_id) -> Response:
        """Renvoie le code de fin par SMS (2 fois sur demande, en plus de l'envoi automatique)."""
        booking = booking_for_client(user=request.user, public_id=public_id)
        send_completion_code_sms(booking=booking, actor=request.user)
        booking = booking_for_client(user=request.user, public_id=public_id)
        return Response(ClientBookingSerializer(booking).data)


class BookingPhotoReportView(APIView):
    permission_classes = [IsClient]

    @extend_schema(
        tags=["bookings"],
        operation_id="bookings_photos_report",
        request=None,
        responses={200: ClientBookingSerializer, **ERRORS},
    )
    def post(self, request: Request, public_id, photo_id) -> Response:
        """« Signaler cette photo » : masquée pour le client et le pro, gardée pour l'Ops.
        Rejoué : 200."""
        booking = booking_for_client(user=request.user, public_id=public_id)
        report_photo(booking=booking, photo_public_id=photo_id, actor=request.user)
        booking = booking_for_client(user=request.user, public_id=public_id)
        return Response(ClientBookingSerializer(booking).data)


class BookingAmendmentDecisionView(APIView):
    """Le client décide d'un avenant, depuis sa session seulement (ni le pro, ni un lien SMS)."""

    permission_classes = [IsClient]
    accept = True

    def post(self, request: Request, public_id, amendment_id) -> Response:
        amendment = amendment_for_client(
            user=request.user, booking_public_id=public_id, public_id=amendment_id
        )
        decide = accept_amendment if self.accept else decline_amendment
        decide(amendment=amendment, actor=request.user)
        booking = booking_for_client(user=request.user, public_id=public_id)
        return Response(ClientBookingSerializer(booking).data)


DECISION_ERRORS = {
    409: error("amendment_not_pending, transition_not_allowed"),
    **ERRORS,
}


class BookingAmendmentAcceptView(BookingAmendmentDecisionView):
    accept = True

    @extend_schema(
        tags=["bookings"],
        operation_id="bookings_amendments_accept",
        request=None,
        responses={200: ClientBookingSerializer, **DECISION_ERRORS},
    )
    def post(self, request: Request, public_id, amendment_id) -> Response:
        """Accepte l'avenant : le montant de la réservation devient son total. Rejoué : 200."""
        return super().post(request, public_id, amendment_id)


class BookingAmendmentDeclineView(BookingAmendmentDecisionView):
    accept = False

    @extend_schema(
        tags=["bookings"],
        operation_id="bookings_amendments_decline",
        request=None,
        responses={200: ClientBookingSerializer, **DECISION_ERRORS},
    )
    def post(self, request: Request, public_id, amendment_id) -> Response:
        """Refuse l'avenant : le travail continue au prix courant. Rejoué : 200."""
        return super().post(request, public_id, amendment_id)


# --- Côté pro ----------------------------------------------------------------------------------


def owned_provider(request: Request) -> Provider:
    """La fiche du gérant, suspendue comprise (lecture) ; 404 s'il n'en a pas."""
    provider = provider_for_owner(request.user)
    if provider is None:
        raise DomainError("not_found", status=404)
    return provider


class ProBookingListView(generics.ListAPIView):
    permission_classes = [HasOwnerRole]
    serializer_class = ProBookingSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Booking.objects.none()
        return bookings_for_provider(provider=owned_provider(self.request))

    @extend_schema(
        tags=["pro"],
        operation_id="pro_bookings_list",
        responses={200: ProBookingSerializer(many=True), **ERRORS},
    )
    def get(self, request: Request, *args, **kwargs) -> Response:
        return super().get(request, *args, **kwargs)


class ProBookingDetailView(APIView):
    permission_classes = [HasOwnerRole, IsProOwner]

    @extend_schema(
        tags=["pro"],
        operation_id="pro_bookings_retrieve",
        responses={200: ProBookingSerializer, **ERRORS},
    )
    def get(self, request: Request, public_id) -> Response:
        booking = booking_for_provider(provider=owned_provider(request), public_id=public_id)
        self.check_object_permissions(request, booking)
        return Response(ProBookingSerializer(booking).data)


class ProBookingConfirmView(APIView):
    permission_classes = [IsVerifiedPro, IsProOwner]

    @extend_schema(
        tags=["pro"],
        operation_id="pro_bookings_confirm",
        request=None,
        responses={
            200: ProBookingSerializer,
            409: OpenApiResponse(description="transition_not_allowed (déjà confirmée, échue)"),
            **ERRORS,
        },
    )
    def post(self, request: Request, public_id) -> Response:
        booking = booking_for_provider(provider=request.provider, public_id=public_id)
        self.check_object_permissions(request, booking)
        confirm_booking(booking=booking, actor=request.user)
        booking = booking_for_provider(provider=request.provider, public_id=public_id)
        return Response(ProBookingSerializer(booking).data)


class ProBookingCancelView(APIView):
    permission_classes = [IsVerifiedPro, IsProOwner]

    @extend_schema(
        tags=["pro"],
        operation_id="pro_bookings_cancel",
        request=ReasonSerializer,
        responses={
            200: ProBookingSerializer,
            409: OpenApiResponse(description="transition_not_allowed"),
            422: OpenApiResponse(description="reason_invalid, note_invalid"),
            **ERRORS,
        },
    )
    def post(self, request: Request, public_id) -> Response:
        booking = booking_for_provider(provider=request.provider, public_id=public_id)
        self.check_object_permissions(request, booking)
        serializer = ReasonSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        cancel_booking(
            booking=booking, actor=request.user, actor_kind=Actor.PRO,
            **serializer.validated_data,
        )  # fmt: skip
        booking = booking_for_provider(provider=request.provider, public_id=public_id)
        return Response(ProBookingSerializer(booking).data)


class ProBookingProgressView(APIView):
    """Une étape du déroulé (en route, sur place, début) : service, puis la réservation à jour.

    Rejouée une fois l'étape faite : ``200`` avec l'état courant, sans nouvel événement.
    """

    permission_classes = [IsVerifiedPro, IsProOwner]
    input_serializer: type[OccurredAtSerializer] = OccurredAtSerializer

    def run(self, booking: Booking, request: Request, data: dict) -> None:
        raise NotImplementedError

    def post(self, request: Request, public_id) -> Response:
        booking = booking_for_provider(provider=request.provider, public_id=public_id)
        self.check_object_permissions(request, booking)
        serializer = self.input_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.run(booking, request, serializer.validated_data)
        booking = booking_for_provider(provider=request.provider, public_id=public_id)
        return Response(ProBookingSerializer(booking).data)


PROGRESS_ERRORS = {
    409: error("transition_not_allowed (étape non permise depuis ce statut)"),
    422: error("occurred_at_invalid"),
    **ERRORS,
}


class ProBookingEnRouteView(ProBookingProgressView):
    @extend_schema(
        tags=["pro"],
        operation_id="pro_bookings_en_route",
        request=OccurredAtSerializer,
        responses={200: ProBookingSerializer, **PROGRESS_ERRORS},
    )
    def post(self, request: Request, public_id) -> Response:
        return super().post(request, public_id)

    def run(self, booking: Booking, request: Request, data: dict) -> None:
        mark_en_route(booking=booking, actor=request.user, occurred_at=data["occurred_at"])


class ProBookingArriveView(ProBookingProgressView):
    @extend_schema(
        tags=["pro"],
        operation_id="pro_bookings_arrive",
        request=OccurredAtSerializer,
        responses={200: ProBookingSerializer, **PROGRESS_ERRORS},
    )
    def post(self, request: Request, public_id) -> Response:
        return super().post(request, public_id)

    def run(self, booking: Booking, request: Request, data: dict) -> None:
        mark_arrived(booking=booking, actor=request.user, occurred_at=data["occurred_at"])


class ProBookingStartView(ProBookingProgressView):
    input_serializer = StartSerializer

    @extend_schema(
        tags=["pro"],
        operation_id="pro_bookings_start",
        request=StartSerializer,
        responses={
            200: ProBookingSerializer,
            409: error("transition_not_allowed (le début n'est jamais déduit d'une étape manquée)"),
            422: error("before_photos_required, occurred_at_invalid"),
            **ERRORS,
        },
    )
    def post(self, request: Request, public_id) -> Response:
        return super().post(request, public_id)

    def run(self, booking: Booking, request: Request, data: dict) -> None:
        start_work(
            booking=booking,
            actor=request.user,
            photos_pending=data["photos_pending"],
            occurred_at=data["occurred_at"],
        )


class ProBookingContestNoShowView(APIView):
    # Un pro suspendu peut contester : c'est sa défense, pas une nouvelle activité.
    permission_classes = [HasOwnerRole, IsProOwner]

    @extend_schema(
        tags=["pro"],
        operation_id="pro_bookings_contest_no_show",
        request=ContestNoShowSerializer,
        responses={
            200: ProBookingSerializer,
            409: error("no_show_contest_closed, transition_not_allowed"),
            422: error("note_invalid"),
            **ERRORS,
        },
    )
    def post(self, request: Request, public_id) -> Response:
        provider = owned_provider(request)
        booking = booking_for_provider(provider=provider, public_id=public_id)
        self.check_object_permissions(request, booking)
        serializer = ContestNoShowSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        contest_no_show(booking=booking, actor=request.user, note=serializer.validated_data["note"])
        booking = booking_for_provider(provider=provider, public_id=public_id)
        return Response(ProBookingSerializer(booking).data)


class ProBookingCompleteView(APIView):
    # Un pro suspendu peut terminer une intervention en cours (photos, code) : HasOwnerRole.
    permission_classes = [HasOwnerRole, IsProOwner]

    @extend_schema(
        tags=["pro"],
        operation_id="pro_bookings_complete",
        request=CompleteSerializer,
        responses={
            200: ProBookingSerializer,
            409: error("completion_code_locked, transition_not_allowed"),
            422: error(
                "completion_code_invalid, completion_proof_required, no_code_reason_invalid, "
                "after_photos_required, occurred_at_invalid"
            ),
            **ERRORS,
        },
    )
    def post(self, request: Request, public_id) -> Response:
        """Terminer avec le code du client (``code``), ou sans code (``no_code_reason`` :
        client_absent, client_no_phone, code_locked, client_refuses). Rejoué : 200."""
        provider = owned_provider(request)
        booking = booking_for_provider(provider=provider, public_id=public_id)
        self.check_object_permissions(request, booking)
        serializer = CompleteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        complete_work(
            booking=booking,
            actor=request.user,
            code=data["code"],
            no_code_reason=data["no_code_reason"],
            photos_pending=data["photos_pending"],
            occurred_at=data["occurred_at"],
        )
        booking = booking_for_provider(provider=provider, public_id=public_id)
        return Response(ProBookingSerializer(booking).data)


class ProBookingPhotoUploadView(APIView):
    # Un pro suspendu envoie encore pour une intervention en cours (le service le vérifie).
    permission_classes = [HasOwnerRole, IsProOwner]
    parser_classes = [MultiPartParser]

    @extend_schema(
        tags=["pro"],
        operation_id="pro_bookings_photos_upload",
        parameters=[IDEMPOTENCY_PARAMETER],
        request={"multipart/form-data": PhotoUploadSerializer},
        responses={
            201: PhotoSerializer,
            200: OpenApiResponse(PhotoSerializer, description="Rejeu : même photo"),
            400: error("invalid, idempotency_key_required"),
            409: error("photo_limit_reached, idempotency_key_reused, transition_not_allowed"),
            413: error("photo_too_large"),
            422: error("photo_invalid"),
            **ERRORS,
        },
    )
    def post(self, request: Request, public_id) -> Response:
        """Photo « avant » ou « après » (1 à 5 par phase). Réencodée sans EXIF ni GPS ;
        « Photographiez seulement le travail, pas les personnes. »"""
        provider = owned_provider(request)
        booking = booking_for_provider(provider=provider, public_id=public_id)
        self.check_object_permissions(request, booking)
        serializer = PhotoUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        upload = data["file"]
        if upload.size > settings.BOOKING_PHOTO_MAX_BYTES:  # avant toute lecture du contenu
            raise DomainError("photo_too_large", status=413)
        result = upload_photo(
            booking=booking,
            actor=request.user,
            phase=data["phase"],
            content=upload.read(),
            idempotency_key=idempotency_key(request),
            taken_at=data["taken_at"],
        )
        code = status.HTTP_201_CREATED if result.created else status.HTTP_200_OK
        return Response(PhotoSerializer(result.photo).data, status=code)


class ProBookingAmendmentCreateView(APIView):
    permission_classes = [IsVerifiedPro, IsProOwner]

    @extend_schema(
        tags=["pro"],
        operation_id="pro_bookings_amendments_create",
        parameters=[IDEMPOTENCY_PARAMETER],
        request=AmendmentProposeSerializer,
        responses={
            201: AmendmentSerializer,
            200: OpenApiResponse(AmendmentSerializer, description="Rejeu : même avenant"),
            400: error("invalid, idempotency_key_required"),
            409: error(
                "amendment_pending, amendment_limit, idempotency_key_reused, transition_not_allowed"
            ),
            422: error(
                "amendment_total_invalid, amendment_reason_invalid, note_invalid, text_too_long"
            ),
            **ERRORS,
        },
    )
    def post(self, request: Request, public_id) -> Response:
        """Propose le **nouveau prix complet** (pas la différence) pendant l'intervention. Le
        client reçoit un SMS avec l'ancien et le nouveau prix et décide seul."""
        booking = booking_for_provider(provider=request.provider, public_id=public_id)
        self.check_object_permissions(request, booking)
        serializer = AmendmentProposeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        result = propose_amendment(
            booking=booking,
            actor=request.user,
            reason=data["reason"],
            note=data["note"],
            total_xof=data["total_xof"],
            lines=tuple(
                QuoteLineInput(line["kind"], line["amount_xof"], line["label"])
                for line in data["lines"]
            ),
            idempotency_key=idempotency_key(request),
        )
        code = status.HTTP_201_CREATED if result.created else status.HTTP_200_OK
        return Response(AmendmentSerializer(result.amendment).data, status=code)


class ProAmendmentWithdrawView(APIView):
    permission_classes = [IsVerifiedPro, IsProOwner]

    @extend_schema(
        tags=["pro"],
        operation_id="pro_amendments_withdraw",
        request=None,
        responses={200: ProBookingSerializer, **DECISION_ERRORS},
    )
    def post(self, request: Request, amendment_id) -> Response:
        """Retire son avenant tant que le client n'a pas décidé. Rejoué : 200."""
        amendment = amendment_for_provider(provider=request.provider, public_id=amendment_id)
        self.check_object_permissions(request, amendment.booking)
        withdraw_amendment(amendment=amendment, actor=request.user)
        booking = booking_for_provider(
            provider=request.provider, public_id=amendment.booking.public_id
        )
        return Response(ProBookingSerializer(booking).data)
