"""Commandes de démonstration (spec 003) : locales seulement, par les services."""

from io import StringIO

import pytest
from django.core.management import CommandError, call_command

from jeflink.accounts.tests.factories import CompleteUserFactory
from jeflink.bookings.models import Booking
from jeflink.catalog.tests.factories import TradeFactory
from jeflink.providers.models import Provider
from jeflink.requests.models import Quote, ServiceRequest
from jeflink.requests.tests.factories import ServiceRequestFactory
from jeflink.zones.tests.factories import ZoneFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def local(settings):
    settings.DJANGO_ENV = "local"


def run(name, *args):
    out = StringIO()
    call_command(name, *args, stdout=out)
    return out.getvalue()


@pytest.fixture
def demo(local):
    trade = TradeFactory()
    zone = ZoneFactory(trades=[trade])
    run("seed_demo_pros")
    return trade, zone


def test_refuse_hors_local(settings):
    settings.DJANGO_ENV = "test"
    for name, args in (("seed_demo_pros", ()), ("demo_pro", ("list",))):
        with pytest.raises(CommandError, match="refusée hors"):
            run(name, *args)
    settings.DJANGO_ENV = "production"
    with pytest.raises(CommandError):
        run("seed_demo_pros")


def test_seed_sans_catalogue(local):
    with pytest.raises(CommandError, match="seed"):
        run("seed_demo_pros")


def test_seed_cree_trois_pros_verifies_et_est_idempotent(demo):
    trade, zone = demo
    pros = Provider.objects.filter(is_demo=True)
    assert pros.count() == 3
    assert all(p.status == "verified" for p in pros)
    assert all(trade in p.trades.all() and zone in p.zones.all() for p in pros)
    run("seed_demo_pros")
    assert Provider.objects.count() == 3


def test_autoquote_confirm_parcours_complet(demo, api_client):
    trade, zone = demo
    client = CompleteUserFactory()
    request = ServiceRequestFactory(client=client, trade=trade, zone=zone)
    out = run("demo_pro", "autoquote", str(request.public_id))
    assert "3 devis envoyé(s)" in out
    assert Quote.objects.filter(request=request).count() == 3
    request.refresh_from_db()
    assert request.status == ServiceRequest.Status.QUOTED
    # Un 4e pro n'a pas de place : le même appel ne change rien.
    assert "0 devis envoyé(s)" in run("demo_pro", "autoquote", str(request.public_id))
    from jeflink.bookings.services import create_from_quote

    quote = Quote.objects.filter(request=request).order_by("slot_start").first()
    booking = create_from_quote(quote=quote, actor=client).booking
    assert "confirmée" in run("demo_pro", "confirm", str(booking.public_id))
    booking.refresh_from_db()
    assert booking.status == Booking.Status.SCHEDULED


def test_list_quote_withdraw_cancel(demo):
    trade, zone = demo
    request = ServiceRequestFactory(trade=trade, zone=zone)
    assert str(request.public_id) in run("demo_pro", "list")
    out = run("demo_pro", "quote", str(request.public_id), "--pro", "2", "--amount", "9000")
    quote = Quote.objects.get(request=request)
    assert str(quote.public_id) in out and quote.total_xof == 9000
    run("demo_pro", "withdraw", str(quote.public_id))
    quote.refresh_from_db()
    assert quote.status == "withdrawn"
    run("demo_pro", "quote", str(request.public_id), "--visit", "--amount", "10000")
    visit = Quote.objects.get(request=request, status="submitted")
    assert visit.kind == "visit" and visit.visit_deductible
    from jeflink.bookings.services import create_from_quote

    booking = create_from_quote(quote=visit, actor=request.client).booking
    run("demo_pro", "cancel", str(booking.public_id), "--reason", "too_far")
    booking.refresh_from_db()
    assert (booking.status, booking.cancelled_by) == ("cancelled", "pro")


def test_erreurs_claires(demo):
    with pytest.raises(CommandError, match="invalide"):
        run("demo_pro", "autoquote", "pas-un-uuid")
    request = ServiceRequestFactory()
    with pytest.raises(CommandError, match="--pro"):
        run("demo_pro", "quote", str(request.public_id), "--pro", "9")
    with pytest.raises(CommandError):
        run("demo_pro", "confirm", "00000000-0000-0000-0000-000000000000")


def test_demo_pro_sans_pro_de_demo(local):
    with pytest.raises(CommandError, match="seed_demo_pros"):
        run("demo_pro", "list")
