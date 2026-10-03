import factory
from django.contrib.gis.geos import Point

from jeflink.zones.models import City, Zone


class CityFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = City
        django_get_or_create = ("slug",)

    slug = "dakar"
    name = "Dakar"


class ZoneFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Zone
        skip_postgeneration_save = True

    city = factory.SubFactory(CityFactory)
    slug = factory.Sequence(lambda n: f"zone-{n}")
    name = factory.Sequence(lambda n: f"Zone {n}")
    center = Point(-17.4400, 14.7600, srid=4326)
    radius_m = 1500

    @factory.post_generation
    def trades(self, create, extracted, **kwargs):
        if create and extracted:
            self.trades.add(*extracted)
