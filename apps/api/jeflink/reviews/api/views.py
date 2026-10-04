"""Avis (spec 004) : permissions, désérialisation, service, sérialisation."""

from drf_spectacular.utils import extend_schema
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from jeflink.accounts.permissions import IsClient
from jeflink.bookings.api.serializers import ClientBookingSerializer
from jeflink.bookings.api.views import ERRORS, error
from jeflink.bookings.selectors import booking_for_client
from jeflink.reviews.services import submit_review

from .serializers import ReviewWriteSerializer


class BookingReviewView(APIView):
    permission_classes = [IsClient]

    @extend_schema(
        tags=["bookings"],
        operation_id="bookings_review_put",
        request=ReviewWriteSerializer,
        responses={
            200: ClientBookingSerializer,
            409: error("review_window_closed, review_not_allowed"),
            422: error("review_invalid"),
            **ERRORS,
        },
    )
    def put(self, request: Request, public_id) -> Response:
        """Note le pro : une note suffit, les puces et le commentaire sont facultatifs. Modifiable
        dans le délai (14 jours après « terminé »). Publié à la clôture de la réservation."""
        booking = booking_for_client(user=request.user, public_id=public_id)
        serializer = ReviewWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        submit_review(booking=booking, actor=request.user, **serializer.validated_data)
        booking = booking_for_client(user=request.user, public_id=public_id)
        return Response(ClientBookingSerializer(booking).data)
