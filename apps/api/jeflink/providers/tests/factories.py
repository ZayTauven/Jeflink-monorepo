import factory

from jeflink.accounts.models import Role, RoleGrant
from jeflink.accounts.tests.factories import CompleteUserFactory
from jeflink.providers.models import Provider


class ProviderFactory(factory.django.DjangoModelFactory):
    """Fiche pro avec le rôle ``owner`` de son gérant. ``trades`` et ``zones`` à passer."""

    class Meta:
        model = Provider
        skip_postgeneration_save = True

    owner = factory.SubFactory(CompleteUserFactory)
    business_name = factory.Sequence(lambda n: f"Pro {n}")
    status = Provider.Status.PENDING

    @factory.post_generation
    def role(self, create, extracted, **kwargs):
        if create:
            RoleGrant.objects.get_or_create(
                user=self.owner, role=Role.OWNER, defaults={"reason_code": "test"}
            )

    @factory.post_generation
    def trades(self, create, extracted, **kwargs):
        if create and extracted:
            self.trades.add(*extracted)

    @factory.post_generation
    def zones(self, create, extracted, **kwargs):
        if create and extracted:
            self.zones.add(*extracted)


class VerifiedProviderFactory(ProviderFactory):
    status = Provider.Status.VERIFIED
