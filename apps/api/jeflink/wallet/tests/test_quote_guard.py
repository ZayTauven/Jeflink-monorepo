"""Seuils de dette (spec 005, tâche 7) : au-delà du seuil de blocage, nouveaux devis refusés et
rien d'autre ; une déclaration en attente lève le blocage ; relance des pros endettés."""

import uuid
from datetime import timedelta

import pytest
from django.utils import timezone

from jeflink.bookings.machine import Status
from jeflink.bookings.models import Booking
from jeflink.bookings.tests.factories import accept, advance, confirm, make_scene, quote_input
from jeflink.bookings.tests.test_pro_api import pro_api, send_quote, world  # noqa: F401
from jeflink.common.errors import DomainError
from jeflink.notifications import events
from jeflink.payments import services as payments
from jeflink.payments.models import SettlementChannel
from jeflink.payments.tests.test_settlements import owe
from jeflink.providers.tests.factories import VerifiedProviderFactory
from jeflink.requests import quotes
from jeflink.requests.models import Quote
from jeflink.requests.tests.factories import ServiceRequestFactory
from jeflink.wallet.models import LedgerAccount
from jeflink.wallet.services import remind_debts

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _seuils(settings):
    settings.WALLET_DEBT_ALERT_XOF = 10_000
    settings.WALLET_DEBT_BLOCK_XOF = 25_000


@pytest.fixture
def notified(monkeypatch):
    sent = []
    monkeypatch.setattr(
        events, "notify", lambda kind, recipients, ref: sent.append((kind, list(recipients), ref))
    )
    return sent


def submit(provider, request):
    return quotes.submit_quote(
        provider=provider,
        request=request,
        content=quote_input(),
        idempotency_key=uuid.uuid4().hex,
    )


def new_request_for(provider):
    return ServiceRequestFactory(trade=provider.trades.first(), zone=provider.zones.first())


def declare(provider, amount):
    wave, _ = SettlementChannel.objects.get_or_create(
        slug="wave", defaults={"gateway": "manual_mobile_money", "label_fr": "Wave"}
    )
    return payments.declare_settlement(
        provider=provider,
        actor=provider.owner,
        channel=wave,
        amount_xof=amount,
        reference=f"T_{uuid.uuid4().hex[:10].upper()}",
        paid_at=timezone.now(),
        payer_last4="",
        idempotency_key=uuid.uuid4().hex,
    ).intent


# --- Garde des devis ---------------------------------------------------------------------------


def test_au_dela_du_seuil_un_nouveau_devis_est_refuse():
    scene = make_scene(pros=1)
    provider = scene.providers[0]
    owe(provider, 25_000)

    with pytest.raises(DomainError) as exc:
        submit(provider, new_request_for(provider))
    assert (exc.value.code, exc.value.status_code) == ("commission_debt_over_limit", 409)
    assert Quote.objects.filter(provider=provider).count() == 1  # celui de la scène seulement


def test_sous_le_seuil_le_devis_passe_meme_en_alerte():
    scene = make_scene(pros=1)
    provider = scene.providers[0]
    owe(provider, 24_999)
    assert submit(provider, new_request_for(provider)).created


def test_une_declaration_en_attente_leve_le_blocage_et_son_rejet_le_retablit(user_factory):
    scene = make_scene(pros=1)
    provider = scene.providers[0]
    owe(provider, 30_000)
    intent = declare(provider, 10_000)
    assert submit(provider, new_request_for(provider)).created

    payments.reject_settlement(intent=intent, operator=user_factory(), reason="other", note="")
    with pytest.raises(DomainError):
        submit(provider, new_request_for(provider))


def test_le_blocage_ne_touche_ni_la_confirmation_ni_la_mission_en_cours():
    scene = make_scene(pros=1)
    booking = accept(scene)
    owe(booking.provider, 50_000)

    booking = confirm(booking)  # réservation déjà acceptée : confirmée malgré la dette
    assert booking.status == Status.SCHEDULED
    now = timezone.now()
    Booking.objects.filter(pk=booking.pk).update(
        slot_start=now - timedelta(hours=1), slot_end=now + timedelta(hours=3)
    )
    booking.refresh_from_db()
    assert advance(booking, Status.COMPLETED).status == Status.COMPLETED


def test_l_api_repond_409_commission_debt_over_limit(api_client, world):  # noqa: F811
    owe(world["pro"], 25_000)
    response = send_quote(pro_api(api_client, world["pro"]), world["request"])
    assert (response.status_code, response.json()["code"]) == (409, "commission_debt_over_limit")


# --- Relances ----------------------------------------------------------------------------------


def test_les_pros_endettes_sont_relances_une_fois_par_semaine(notified):
    indebted, small = VerifiedProviderFactory(), VerifiedProviderFactory()
    owe(indebted, 12_000)
    owe(small, 3_000)

    assert remind_debts() == 1
    assert notified == [(events.WALLET_DEBT_REMINDER, [indebted.owner], indebted.public_id)]
    assert remind_debts() == 0  # déjà relancé cette semaine
    assert remind_debts(now=timezone.now() + timedelta(days=8)) == 1
    account = LedgerAccount.objects.get(provider=indebted)
    assert account.last_reminder_at is not None


def test_une_dette_couverte_par_une_declaration_n_est_pas_relancee(notified):
    provider = VerifiedProviderFactory()
    owe(provider, 12_000)
    declare(provider, 5_000)
    assert remind_debts() == 0
