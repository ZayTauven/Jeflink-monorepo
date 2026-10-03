"""Scénario de réservation pour les tests : demande, pro vérifié, devis, acceptation."""

from dataclasses import dataclass, field
from datetime import timedelta

from django.utils import timezone

from jeflink.bookings import services
from jeflink.bookings.machine import Actor, Status
from jeflink.bookings.models import Booking
from jeflink.catalog.tests.factories import TradeFactory
from jeflink.common.dakar import dakar_today
from jeflink.providers.models import Provider
from jeflink.providers.tests.factories import VerifiedProviderFactory
from jeflink.requests import quotes
from jeflink.requests.models import Quote, ServiceRequest
from jeflink.requests.quotes import QuoteInput, QuoteLineInput
from jeflink.requests.tests.factories import ServiceRequestFactory
from jeflink.zones.tests.factories import ZoneFactory

_counter = iter(range(100_000))


@dataclass
class Scene:
    trade: object
    zone: object
    request: ServiceRequest
    providers: list[Provider] = field(default_factory=list)
    quotes: list[Quote] = field(default_factory=list)

    @property
    def client(self):
        return self.request.client


def quote_input(*, days: int = 1, period: str = "morning", amount: int = 15_000) -> QuoteInput:
    return QuoteInput(
        kind="fixed",
        total_xof=amount,
        lines=(QuoteLineInput("labor", amount, "Intervention"),),
        slot_day=dakar_today(timezone.now()) + timedelta(days=days),
        slot_period=period,
    )


def make_scene(*, pros: int = 2, urgent: bool = False) -> Scene:
    """Une demande ouverte et ``pros`` pros vérifiés qui ont chacun envoyé un devis."""
    trade = TradeFactory()
    zone = ZoneFactory(trades=[trade])
    request = ServiceRequestFactory(trade=trade, zone=zone, urgent=urgent)
    scene = Scene(trade, zone, request)
    for index in range(pros):
        provider = VerifiedProviderFactory(trades=[trade], zones=[zone])
        created = quotes.submit_quote(
            provider=provider,
            request=request,
            content=quote_input(days=1 + index),
            idempotency_key=f"scene-quote-{next(_counter):020d}",
        )
        scene.providers.append(provider)
        scene.quotes.append(created.quote)
    request.refresh_from_db()
    return scene


def accept(scene: Scene, index: int = 0) -> Booking:
    created = services.create_from_quote(quote=scene.quotes[index], actor=scene.client)
    return created.booking


def confirm(booking: Booking) -> Booking:
    return services.confirm_booking(booking=booking, actor=booking.provider.owner)


def scheduled(*, pros: int = 1, urgent: bool = False) -> tuple[Scene, Booking]:
    """Une réservation confirmée par le pro (``scheduled``)."""
    scene = make_scene(pros=pros, urgent=urgent)
    return scene, confirm(accept(scene))


def advance(booking: Booking, to: str) -> Booking:
    """Fait avancer une réservation ``scheduled`` jusqu'à ``to`` par les services du pro.

    ``in_progress`` passe par ``photos_pending`` ; ``completed`` par la transition directe (le
    code de fin et les photos sont testés à part).
    """
    owner = booking.provider.owner
    steps = [
        (Status.EN_ROUTE, lambda b: services.mark_en_route(booking=b, actor=owner)),
        (Status.ON_SITE, lambda b: services.mark_arrived(booking=b, actor=owner)),
        (
            Status.IN_PROGRESS,
            lambda b: services.start_work(booking=b, actor=owner, photos_pending=True),
        ),
        (
            Status.COMPLETED,
            lambda b: services.transition(
                b, to=Status.COMPLETED, actor=owner, actor_kind=Actor.PRO, reason="test"
            ),
        ),
    ]
    for status, step in steps:
        booking = step(booking)
        if status == to:
            break
    booking.refresh_from_db()
    return booking
