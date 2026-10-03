import factory

from jeflink.accounts.models import Role, RoleGrant, User


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User
        skip_postgeneration_save = True

    phone = factory.Sequence(lambda n: f"+22177{n:07d}")
    password = factory.PostGenerationMethodCall("set_unusable_password")


class CompleteUserFactory(UserFactory):
    display_name = factory.Sequence(lambda n: f"Awa {n}")
    profile_status = User.ProfileStatus.COMPLETE


class RoleGrantFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = RoleGrant

    user = factory.SubFactory(UserFactory)
    role = Role.OWNER
    reason_code = "test"
