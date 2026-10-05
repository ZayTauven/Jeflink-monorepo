"""Démo du portefeuille (spec 005, tâche 10) : la commission de clôture, la déclaration du pro,
la confirmation de l'Ops ; local seulement."""

from datetime import timedelta
from io import StringIO

import pytest
from django.core.management import CommandError, call_command
from django.utils import timezone

from jeflink.accounts.tests.factories import CompleteUserFactory
from jeflink.bookings import services as bookings
from jeflink.bookings.machine import Status
from jeflink.bookings.models import Booking
from jeflink.bookings.tests.factories import advance, make_scene
from jeflink.payments import services as payments
from jeflink.payments.models import PaymentIntent, SettlementChannel
from jeflink.providers.models import Provider
from jeflink.wallet.selectors import provider_balance

pytestmark = pytest.mark.django_db


def run(command, *args):
    out = StringIO()
    call_command(command, *args, stdout=out)
    return out.getvalue()


@pytest.fixture
def closed(settings):
    """Une mission d'un pro de démo, close par la fenêtre de contestation (15 000 F)."""
    settings.DJANGO_ENV = "local"
    scene = make_scene(pros=1)
    Provider.objects.filter(pk=scene.providers[0].pk).update(is_demo=True)
    booking = bookings.create_from_quote(quote=scene.quotes[0], actor=scene.client).booking
    run("demo_pro", "confirm", str(booking.public_id))
    now = timezone.now()
    Booking.objects.filter(pk=booking.pk).update(
        slot_start=now - timedelta(hours=1), slot_end=now + timedelta(hours=3)
    )
    booking.refresh_from_db()
    booking = advance(booking, Status.COMPLETED)
    Booking.objects.filter(pk=booking.pk).update(dispute_deadline=now - timedelta(minutes=1))
    bookings.close_due()
    return booking


def test_parcours_commission_declaration_confirmation(closed):
    out = run("demo_pro", "wallet")
    assert "doit 1500 XOF" in out and "commission · +1500 XOF" in out

    assert "3 canal" in run("seed_settlement_channels")
    assert "0 canal" in run("seed_settlement_channels")  # idempotent
    assert "1500 XOF" in run("demo_pro", "pay", "--amount", "1500")
    intent = PaymentIntent.objects.get()
    assert (intent.channel.slug, intent.status, intent.reference[:4]) == (
        "wave-demo",
        "declared",
        "DEMO",
    )
    assert "en attente 1500" in run("demo_pro", "wallet")

    # L'Ops confirme (dans l'admin, groupe Rapprochement) : le solde revient à 0.
    payments.confirm_settlement(intent=intent, operator=CompleteUserFactory(), received_xof=1_500)
    assert provider_balance(closed.provider).due_xof == 0
    assert "doit 0 XOF" in run("demo_pro", "wallet")


def test_les_canaux_de_demo_ne_sont_jamais_factices_cote_passerelle(settings):
    settings.DJANGO_ENV = "local"
    run("seed_settlement_channels")
    gateways = set(SettlementChannel.objects.values_list("gateway", flat=True))
    assert gateways == {"manual_mobile_money", "cash"}


def test_hors_local_les_commandes_de_demo_sont_refusees(settings):
    settings.DJANGO_ENV = "staging"
    with pytest.raises(CommandError, match="local"):
        run("seed_settlement_channels")
    with pytest.raises(CommandError, match="local"):
        run("demo_pro", "pay", "--amount", "1000")
