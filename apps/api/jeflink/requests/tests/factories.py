from datetime import timedelta

import factory
from django.utils import timezone

from jeflink.accounts.tests.factories import CompleteUserFactory
from jeflink.catalog.tests.factories import TradeFactory
from jeflink.requests.models import ServiceRequest
from jeflink.requests.services import dispatch_rank
from jeflink.zones.tests.factories import ZoneFactory


class ServiceRequestFactory(factory.django.DjangoModelFactory):
    """Demande ``open`` valide. ``trade`` et ``zone`` sont indépendants : à relier au besoin."""

    class Meta:
        model = ServiceRequest

    client = factory.SubFactory(CompleteUserFactory)
    trade = factory.SubFactory(TradeFactory)
    zone = factory.SubFactory(ZoneFactory)
    landmark = "près de la boutique, portail bleu"
    description = "Fuite sous l'évier de la cuisine"
    status = ServiceRequest.Status.OPEN
    channel = ServiceRequest.Channel.WEB
    expires_at = factory.LazyFunction(lambda: timezone.now() + timedelta(hours=72))
    urgent = False
    dispatch_rank = factory.LazyAttribute(
        lambda o: dispatch_rank(urgent=o.urgent, now=timezone.now())
    )
    idempotency_key = factory.Sequence(lambda n: f"factory-key-{n:020d}")
    payload_hash = factory.Sequence(lambda n: f"{n:064d}")
