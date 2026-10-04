from io import StringIO

import pytest
from django.contrib.auth.models import Group
from django.core.management import CommandError, call_command
from django.test import RequestFactory
from rest_framework.request import Request

from jeflink.accounts.models import Role
from jeflink.accounts.permissions import IsProOwner, IsVerifiedPro
from jeflink.accounts.services import grant_role
from jeflink.catalog.tests.factories import TradeFactory
from jeflink.providers.models import Provider
from jeflink.zones.tests.factories import ZoneFactory

from .factories import ProviderFactory, VerifiedProviderFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def admin_user(user_factory):
    user = user_factory()
    grant_role(user=user, role=Role.OPS, reason_code="t", operator="a", second_operator="b")
    user.groups.add(Group.objects.get(name="Admin"))
    return user


def run(*args):
    out = StringIO()
    call_command("onboard_provider", *args, stdout=out)
    return out.getvalue()


def test_commande_onboard_provider(admin_user, complete_user_factory):
    trade, zone = TradeFactory(slug="plomberie"), ZoneFactory(slug="ouakam")
    user = complete_user_factory()
    out = run(
        *("--phone", user.phone, "--name", "Plomberie Ibou", "--trades", "plomberie"),
        *("--zones", "ouakam", "--operator", str(admin_user.public_id)),
    )
    provider = Provider.objects.get(owner=user)
    assert provider.status == "pending"
    assert list(provider.trades.all()) == [trade]
    assert list(provider.zones.all()) == [zone]
    assert str(provider.public_id) in out


def test_commande_refuse_un_operateur_non_admin(user_factory, complete_user_factory):
    user = complete_user_factory()
    with pytest.raises(CommandError):
        run(
            *("--phone", user.phone, "--name", "Ibou", "--trades", "x", "--zones", "y"),
            *("--operator", str(user_factory().public_id)),
        )


def test_commande_refuse_un_metier_inconnu(admin_user, complete_user_factory):
    user = complete_user_factory()
    with pytest.raises(CommandError):
        run(
            *("--phone", user.phone, "--name", "Ibou", "--trades", "inconnu", "--zones", "y"),
            *("--operator", str(admin_user.public_id)),
        )


def make_request(user):
    request = Request(RequestFactory().get("/"))
    request.user = user
    request.auth = {}
    return request


def test_is_verified_pro():
    verified, pending = VerifiedProviderFactory(), ProviderFactory()
    suspended = ProviderFactory(status="suspended")
    assert IsVerifiedPro().has_permission(make_request(verified.owner), None)
    for provider in (pending, suspended):
        permission = IsVerifiedPro()
        assert not permission.has_permission(make_request(provider.owner), None)
        assert permission.code == "provider_not_verified"


def test_is_verified_pro_refuse_un_client_simple(complete_user_factory):
    permission = IsVerifiedPro()
    assert not permission.has_permission(make_request(complete_user_factory()), None)
    assert permission.code == "role_required"


def test_is_proowner_controle_l_objet():
    mine, other = VerifiedProviderFactory(), VerifiedProviderFactory()

    class Obj:
        provider = mine

    request = make_request(mine.owner)
    assert IsProOwner().has_object_permission(request, None, Obj())
    assert not IsProOwner().has_object_permission(make_request(other.owner), None, Obj())
    assert not IsProOwner().has_object_permission(request, None, object())
