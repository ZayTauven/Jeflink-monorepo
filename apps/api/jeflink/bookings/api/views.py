"""Vues des réservations (spec 003) : permissions, désérialisation, service, sérialisation.

Un objet d'un autre utilisateur répond 404. Une fiche pro suspendue lit encore ses réservations
(``HasOwnerRole`` + ``IsProOwner``) mais n'écrit plus (``IsVerifiedPro``).
"""

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import generics, status
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
    booking_for_client,
    booking_for_provider,
    bookings_for_client,
    bookings_for_provider,
)
from jeflink.bookings.services import cancel_booking, confirm_booking, create_from_quote
from jeflink.common.errors import DomainError
from jeflink.providers.models import Provider
from jeflink.providers.selectors import provider_for_owner
from jeflink.requests.api.serializers import ReasonSerializer
from jeflink.requests.selectors import quote_for_client

from .serializers import ClientBookingSerializer, ProBookingSerializer

ERRORS = {
    401: OpenApiResponse(description="not_authenticated"),
    403: OpenApiResponse(description="profile_incomplete, role_required, provider_not_verified"),
    404: OpenApiResponse(description="not_found"),
}


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

    @extend_schema(tags=["bookings"], operation_id="bookings_list", responses=ERRORS)
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

    @extend_schema(tags=["pro"], operation_id="pro_bookings_list", responses=ERRORS)
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
