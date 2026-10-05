"""Commission à la clôture (spec 005, tâche 3) : chaque cas du tableau, idempotence, taux du
devis, seuils de dette, clôtures simultanées."""

import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest
from django.db import DatabaseError, connection, transaction
from django.utils import timezone

from jeflink.bookings import services as bookings
from jeflink.bookings.machine import Actor, Status
from jeflink.bookings.models import Booking
from jeflink.bookings.tests.factories import advance, scheduled
from jeflink.bookings.tests.test_disputes import TEXT, ops_user
from jeflink.notifications import events
from jeflink.trust.models import AuditEvent, Dispute
from jeflink.wallet.models import Commission, CommissionRate, LedgerTransaction
from jeflink.wallet.selectors import provider_balance, provider_wallet
from jeflink.wallet.services import charge_commission_on_close

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _second_facteur_valide(monkeypatch):
    monkeypatch.setattr("jeflink.accounts.admin_site.admin_mfa_valid", lambda request: True)


@pytest.fixture
def notified(monkeypatch):
    sent = []
    monkeypatch.setattr(
        events, "notify", lambda kind, recipients, ref: sent.append((kind, list(recipients), ref))
    )
    return sent


def completed(**fields):
    """Réservation terminée (15 000 F, devis de la scène), ``fields`` écrits à la fin."""
    scene, booking = scheduled()
    booking = advance(booking, Status.IN_PROGRESS)
    booking = bookings.transition(
        booking,
        to=Status.COMPLETED,
        actor=booking.provider.owner,
        actor_kind=Actor.PRO,
        reason="test",
        fields=fields or None,
    )
    return scene, booking


def close(booking) -> Booking:
    Booking.objects.filter(pk=booking.pk).update(
        dispute_deadline=timezone.now() - timedelta(minutes=1)
    )
    bookings.close_due()
    booking.refresh_from_db()
    assert booking.status == Status.CLOSED
    return booking


def commission_of(booking) -> Commission:
    return Commission.objects.get(booking=booking)


# --- Cas du tableau ----------------------------------------------------------------------------


def test_fin_par_code_close_par_la_fenetre_commission_due_au_taux_par_defaut():
    _, booking = completed()
    booking = close(booking)

    commission = commission_of(booking)
    assert (commission.status, commission.amount_xof) == ("charged", 1_500)
    assert (commission.base_xof, commission.rate_bps, commission.cap_xof) == (15_000, 1_000, 20_000)
    assert commission.close_reason == "window_elapsed"
    assert commission.ledger_transaction.kind == "commission"
    assert provider_balance(booking.provider).due_xof == 1_500
    event = AuditEvent.objects.get(action="wallet.commission.recorded")
    assert event.metadata["status"] == "charged" and event.metadata["amount_xof"] == 1_500


def test_fin_sans_code_commission_due_comme_une_fin_par_code():
    _, booking = completed(completion_method="no_code", no_code_reason="client_absent")
    commission = commission_of(close(booking))

    assert (commission.status, commission.amount_xof) == ("charged", 1_500)
    assert commission.completion_method == "no_code"


@pytest.mark.parametrize("decision", Dispute.Decision.values)
def test_litige_tranche_commission_due_quelle_que_soit_la_decision(decision):
    scene, booking = completed()
    bookings.open_dispute(
        booking=booking, actor=scene.client, reason="poor_quality", description=TEXT
    )
    bookings.resolve_dispute(
        dispute=Dispute.objects.get(booking=booking),
        decision=decision,
        note="Décision après appel des deux parties.",
        operator=ops_user(),
    )

    commission = commission_of(booking)
    assert (commission.status, commission.amount_xof) == ("charged", 1_500)
    assert commission.close_reason == f"dispute_{decision}"


def test_client_compte_de_revue_exempte_sans_ecriture():
    scene, booking = completed()
    scene.client.is_review_account = True
    scene.client.save(update_fields=["is_review_account"])
    commission = commission_of(close(booking))

    assert (commission.status, commission.exempt_reason) == ("exempt", "review_account")
    assert commission.ledger_transaction is None
    assert not LedgerTransaction.objects.exists()


def test_taux_de_zero_exempte(notified):
    scene, booking = completed()
    CommissionRate.objects.create(
        trade=scene.trade, rate_bps=0, valid_from=booking.quote.created_at - timedelta(seconds=1)
    )
    commission = commission_of(close(booking))

    assert (commission.status, commission.exempt_reason, commission.rate_bps) == (
        "exempt",
        "zero_rate",
        0,
    )
    assert not LedgerTransaction.objects.exists()


def test_montant_arrondi_a_zero_exempte():
    scene, booking = completed()
    CommissionRate.objects.create(
        trade=scene.trade, rate_bps=6, valid_from=booking.quote.created_at - timedelta(seconds=1)
    )  # 15 000 * 6 // 10 000 = 9 F
    Booking.objects.filter(pk=booking.pk).update(amount_xof=1_000)  # 0,6 F : arrondi à 0
    commission = commission_of(close(booking))

    assert (commission.status, commission.exempt_reason, commission.amount_xof) == (
        "exempt",
        "zero_amount",
        0,
    )


def test_aucun_taux_applicable_exempte_et_alerte(monkeypatch, caplog):
    monkeypatch.setattr("jeflink.wallet.services.rate_for", lambda **kwargs: None)
    _, booking = completed()
    with caplog.at_level(logging.WARNING, logger="jeflink.alerts"):
        commission = commission_of(close(booking))

    assert (commission.status, commission.exempt_reason) == ("exempt", "rate_missing")
    assert commission.rate is None and commission.rate_bps is None
    assert "wallet_rate_missing" in caplog.text


def test_pro_de_demo_commission_due():
    _, booking = completed()
    booking.provider.is_demo = True
    booking.provider.save(update_fields=["is_demo"])
    assert commission_of(close(booking)).status == "charged"


def test_reservation_annulee_aucune_commission():
    _, booking = scheduled()
    bookings.transition(
        booking, to=Status.CANCELLED, actor=None, actor_kind=Actor.SYSTEM, reason="test"
    )
    assert not Commission.objects.exists()


# --- Assiette et taux --------------------------------------------------------------------------


def test_l_assiette_est_le_montant_a_la_cloture_avenants_compris():
    _, booking = completed()
    Booking.objects.filter(pk=booking.pk).update(amount_xof=40_000)  # avenant accepté
    assert commission_of(close(booking)).amount_xof == 4_000


def test_le_plafond_s_applique():
    _, booking = completed()
    Booking.objects.filter(pk=booking.pk).update(amount_xof=500_000)
    assert commission_of(close(booking)).amount_xof == 20_000


def test_un_taux_ajoute_apres_le_devis_ne_change_pas_la_commission():
    scene, booking = completed()
    CommissionRate.objects.create(
        trade=scene.trade, rate_bps=500, valid_from=booking.quote.created_at + timedelta(seconds=1)
    )
    commission = commission_of(close(booking))
    assert (commission.rate_bps, commission.amount_xof) == (1_000, 1_500)


def test_le_taux_du_metier_en_vigueur_au_devis_s_applique():
    scene, booking = completed()
    CommissionRate.objects.create(
        trade=scene.trade,
        rate_bps=700,
        cap_xof=20_000,
        valid_from=booking.quote.created_at - timedelta(seconds=1),
    )
    assert commission_of(close(booking)).amount_xof == 1_050


# --- Idempotence -------------------------------------------------------------------------------


def test_le_gestionnaire_appele_deux_fois_n_ecrit_qu_une_commission():
    _, booking = completed()
    booking = close(booking)
    charge_commission_on_close(booking, "window_elapsed")

    assert Commission.objects.filter(booking=booking).count() == 1
    assert LedgerTransaction.objects.count() == 1
    assert provider_balance(booking.provider).due_xof == 1_500


def test_une_commission_ne_se_modifie_pas():
    _, booking = completed()
    commission = commission_of(close(booking))
    with transaction.atomic(), pytest.raises(DatabaseError, match="immuable"):
        Commission.objects.filter(pk=commission.pk).update(amount_xof=1)


# --- Seuils ------------------------------------------------------------------------------------


def test_franchir_les_seuils_previent_le_pro_une_fois_par_franchissement(settings, notified):
    settings.WALLET_DEBT_ALERT_XOF = 1_500
    settings.WALLET_DEBT_BLOCK_XOF = 4_500
    _, first = completed()
    provider = first.provider
    close(first)
    wallet_kinds = [kind for kind, *_ in notified if kind.startswith("wallet.")]
    assert wallet_kinds == [events.WALLET_DEBT_ALERT]
    assert provider_wallet(provider).state == "alert"

    # Deuxième mission du même pro : dette 3 000, toujours en alerte, rien de plus.
    notified.clear()
    second = _second_booking_for(provider)
    close(second)
    assert not [kind for kind, *_ in notified if kind.startswith("wallet.")]

    # Troisième : 4 500, blocage annoncé (SMS) au gérant, référence = la fiche pro.
    third = _second_booking_for(provider)
    close(third)
    blocked = [n for n in notified if n[0] == events.WALLET_QUOTES_BLOCKED]
    assert blocked == [(events.WALLET_QUOTES_BLOCKED, [provider.owner], provider.public_id)]
    assert events.WALLET_QUOTES_BLOCKED in events.SMS_KINDS
    assert provider_wallet(provider).state == "blocked"


def _second_booking_for(provider):
    """Une autre réservation terminée pour le même pro (nouvelle demande du même métier)."""
    from jeflink.bookings.tests.factories import confirm, quote_input
    from jeflink.requests import quotes
    from jeflink.requests.tests.factories import ServiceRequestFactory

    trade, zone = provider.trades.first(), provider.zones.first()
    request = ServiceRequestFactory(trade=trade, zone=zone)
    quote = quotes.submit_quote(
        provider=provider,
        request=request,
        content=quote_input(),
        idempotency_key=f"wallet-{request.public_id}",
    ).quote
    booking = confirm(bookings.create_from_quote(quote=quote, actor=request.client).booking)
    now = timezone.now()
    Booking.objects.filter(pk=booking.pk).update(
        slot_start=now - timedelta(hours=1), slot_end=now + timedelta(hours=3)
    )
    booking.refresh_from_db()
    return advance(booking, Status.COMPLETED)


# --- Concurrence -------------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True, databases="__all__", serialized_rollback=True)
def test_deux_clotures_simultanees_n_ecrivent_qu_une_commission():
    with transaction.atomic():
        _, booking = completed()
    Booking.objects.filter(pk=booking.pk).update(
        dispute_deadline=timezone.now() - timedelta(minutes=1)
    )

    def run(_):
        try:
            return bookings.close_due()
        finally:
            connection.close()

    with ThreadPoolExecutor(2) as pool:
        closed = sorted(pool.map(run, [0, 1]))

    assert closed == [0, 1]
    assert Commission.objects.filter(booking=booking).count() == 1
    assert provider_balance(booking.provider).due_xof == 1_500
