"""Réservations clôturées et avis, sans passer par tout le déroulé (spec 006)."""

from itertools import count

from django.utils import timezone

from jeflink.accounts.tests.factories import CompleteUserFactory
from jeflink.bookings import services
from jeflink.bookings.models import Booking
from jeflink.bookings.tests.factories import quote_input
from jeflink.providers.tests.factories import VerifiedProviderFactory
from jeflink.requests import quotes
from jeflink.requests.tests.factories import ServiceRequestFactory
from jeflink.reviews.models import Review

_keys = count()


def closed_booking(*, trade, zone, provider=None, client=None, status="closed") -> Booking:
    """Une réservation passée à ``status`` (``closed`` par défaut), pour ce métier et cette zone."""
    client = client or CompleteUserFactory()
    request = ServiceRequestFactory(trade=trade, zone=zone, client=client)
    provider = provider or VerifiedProviderFactory(trades=[trade], zones=[zone])
    created = quotes.submit_quote(
        provider=provider,
        request=request,
        content=quote_input(),
        idempotency_key=f"stats-quote-{next(_keys):020d}",
    )
    booking = services.create_from_quote(quote=created.quote, actor=client).booking
    extra = {"cancelled_by": "system"} if status == "cancelled" else {}
    Booking.objects.filter(pk=booking.pk).update(status=status, **extra)
    booking.refresh_from_db()
    return booking


def review_for(booking: Booking, rating: int = 5, **fields) -> Review:
    return Review.objects.create(
        booking=booking,
        provider=booking.provider,
        author=booking.client,
        rating=rating,
        **{"published_at": timezone.now(), **fields},
    )
