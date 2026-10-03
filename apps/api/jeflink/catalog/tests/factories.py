import factory

from jeflink.catalog.models import Service, Trade


class TradeFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Trade

    slug = factory.Sequence(lambda n: f"metier-{n}")
    name_fr = factory.Sequence(lambda n: f"Métier {n}")


class ServiceFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Service

    trade = factory.SubFactory(TradeFactory)
    slug = factory.Sequence(lambda n: f"service-{n}")
    name_fr = factory.Sequence(lambda n: f"Service {n}")
