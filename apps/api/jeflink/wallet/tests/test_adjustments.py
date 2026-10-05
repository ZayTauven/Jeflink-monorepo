"""Ajustements de la Comptabilité (spec 005, tâche 6) : avoir sur une commission,
contre-passation d'un règlement, geste commercial, correction ; motif et note obligatoires,
jamais sur son propre compte, audités et notifiés."""

import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from django.db import connection, transaction
from django.utils import timezone

from jeflink.common.errors import DomainError
from jeflink.notifications import events
from jeflink.payments import services as payments
from jeflink.payments.models import SettlementChannel
from jeflink.providers.tests.factories import VerifiedProviderFactory
from jeflink.trust.models import AuditEvent
from jeflink.wallet import services
from jeflink.wallet.models import LedgerTransaction
from jeflink.wallet.selectors import provider_balance

from .test_commission import close, commission_of, completed

pytestmark = pytest.mark.django_db
NOTE = "Le pro a remboursé le client après le litige."


@pytest.fixture(autouse=True)
def _second_facteur_valide(monkeypatch):
    monkeypatch.setattr("jeflink.accounts.admin_site.admin_mfa_valid", lambda request: True)


@pytest.fixture
def ops(user_factory):
    return user_factory()


@pytest.fixture
def notified(monkeypatch):
    sent = []
    monkeypatch.setattr(
        events, "notify", lambda kind, recipients, ref: sent.append((kind, list(recipients), ref))
    )
    return sent


@pytest.fixture
def commission():
    """Commission de 1 500 F (réservation de 15 000 F close au taux par défaut)."""
    _, booking = completed()
    return commission_of(close(booking))


def key():
    return uuid.uuid4().hex


def code_of(callable_, **kwargs) -> str:
    with pytest.raises(DomainError) as exc:
        callable_(**kwargs)
    return exc.value.code


def waive(commission, operator, amount, **kwargs):
    params = {
        "commission": commission,
        "amount_xof": amount,
        "reason_code": "dispute_refund",
        "note": NOTE,
        "operator": operator,
        "key": key(),
    } | kwargs
    return services.waive_commission(**params)


# --- Avoir sur une commission ------------------------------------------------------------------


def test_un_avoir_partiel_puis_total_ne_depasse_jamais_la_commission(commission, ops, notified):
    provider = commission.provider
    waive(commission, ops, 500)
    assert provider_balance(provider).due_xof == 1_000
    waive(commission, ops, 1_000)
    assert provider_balance(provider).due_xof == 0
    assert code_of(waive, commission=commission, operator=ops, amount=1) == (
        "adjustment_exceeds_remaining"
    )

    events_sent = [n for n in notified if n[0] == events.WALLET_ADJUSTMENT_POSTED]
    assert len(events_sent) == 2 and events_sent[0][1] == [provider.owner]
    audits = AuditEvent.objects.filter(action="wallet.adjustment.posted")
    assert [a.metadata for a in audits.order_by("created_at")] == [
        {"type": "waiver", "amount_xof": 500, "reason_code": "dispute_refund"},
        {"type": "waiver", "amount_xof": 1_000, "reason_code": "dispute_refund"},
    ]
    assert NOTE not in "".join(str(a.metadata) for a in audits)


def test_un_formulaire_rejoue_n_ecrit_qu_un_avoir(commission, ops):
    same = key()
    first = waive(commission, ops, 500, key=same)
    again = waive(commission, ops, 500, key=same)
    assert again.pk == first.pk
    assert AuditEvent.objects.filter(action="wallet.adjustment.posted").count() == 1
    assert provider_balance(commission.provider).due_xof == 1_000


@pytest.mark.parametrize(
    ("kwargs", "code"),
    [
        ({"reason_code": "inconnu"}, "adjustment_reason_invalid"),
        ({"note": ""}, "note_invalid"),
        ({"note": "Rappeler le 77 123 45 67"}, "note_invalid"),
        ({"amount": 0}, "adjustment_amount_invalid"),
        ({"amount": 100.0}, "adjustment_amount_invalid"),
    ],
)
def test_un_avoir_invalide_est_refuse(commission, ops, kwargs, code):
    amount = kwargs.pop("amount", 500)
    assert code_of(waive, commission=commission, operator=ops, amount=amount, **kwargs) == code
    assert not LedgerTransaction.objects.filter(kind="reversal").exists()


def test_jamais_sur_son_propre_compte_pro(commission):
    owner = commission.provider.owner
    assert code_of(waive, commission=commission, operator=owner, amount=500) == (
        "operator_is_provider"
    )


def test_une_commission_exemptee_n_a_pas_d_avoir(ops):
    scene, booking = completed()
    scene.client.is_review_account = True
    scene.client.save(update_fields=["is_review_account"])
    exempt = commission_of(close(booking))
    assert code_of(waive, commission=exempt, operator=ops, amount=1) == "adjustment_not_allowed"


# --- Contre-passation d'un règlement -----------------------------------------------------------


def test_contre_passer_un_reglement_confirme_a_tort_recree_la_dette(commission, ops):
    provider = commission.provider
    wave = SettlementChannel.objects.create(
        slug="wave", gateway="manual_mobile_money", label_fr="Wave"
    )
    intent = payments.declare_settlement(
        provider=provider,
        actor=provider.owner,
        channel=wave,
        amount_xof=1_500,
        reference="T_DOUBLON01",
        paid_at=timezone.now(),
        payer_last4="",
        idempotency_key=key(),
    ).intent
    assert code_of(
        services.reverse_settlement,
        intent=intent,
        reason_code="duplicate_settlement",
        note=NOTE,
        operator=ops,
        key=key(),
    ) == ("adjustment_not_allowed")  # pas encore confirmé : rien à contre-passer
    payments.confirm_settlement(intent=intent, operator=ops, received_xof=1_500)
    assert provider_balance(provider).due_xof == 0

    services.reverse_settlement(
        intent=intent, reason_code="duplicate_settlement", note=NOTE, operator=ops, key=key()
    )
    assert provider_balance(provider).due_xof == 1_500
    assert code_of(
        services.reverse_settlement,
        intent=intent,
        reason_code="duplicate_settlement",
        note=NOTE,
        operator=ops,
        key=key(),
    ) == ("adjustment_exceeds_remaining")


# --- Geste commercial et correction ------------------------------------------------------------


def test_un_geste_commercial_baisse_la_dette_et_peut_creer_un_avoir(commission, ops):
    provider = commission.provider
    services.post_goodwill_credit(
        provider=provider, amount_xof=2_000, reason_code="goodwill", note=NOTE, operator=ops,
        key=key(),
    )  # fmt: skip
    balance = provider_balance(provider)
    assert (balance.due_xof, balance.credit_xof) == (0, 500)


def test_une_correction_augmente_la_dette_et_se_rattache_a_la_reservation(commission, ops):
    provider = commission.provider
    txn = services.post_correction_debit(
        provider=provider, amount_xof=700, reason_code="entry_error", note=NOTE, operator=ops,
        key=key(), booking=commission.booking,
    )  # fmt: skip
    assert txn.booking == commission.booking and txn.kind == "correction_debit"
    assert provider_balance(provider).due_xof == 2_200


def test_une_correction_sur_la_reservation_d_un_autre_pro_est_refusee(commission, ops):
    other = VerifiedProviderFactory()
    assert code_of(
        services.post_correction_debit,
        provider=other,
        amount_xof=700,
        reason_code="entry_error",
        note=NOTE,
        operator=ops,
        key=key(),
        booking=commission.booking,
    ) == ("adjustment_not_allowed")


def test_une_correction_qui_franchit_le_seuil_bloque_les_devis(commission, ops, notified, settings):
    settings.WALLET_DEBT_ALERT_XOF = 1_000
    settings.WALLET_DEBT_BLOCK_XOF = 5_000
    provider = commission.provider
    notified.clear()
    services.post_correction_debit(
        provider=provider, amount_xof=4_000, reason_code="other", note=NOTE, operator=ops,
        key=key(),
    )  # fmt: skip
    assert (events.WALLET_QUOTES_BLOCKED, [provider.owner], provider.public_id) in notified


# --- Concurrence -------------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True, databases="__all__", serialized_rollback=True)
def test_deux_avoirs_simultanes_ne_depassent_pas_la_commission(user_factory):
    with transaction.atomic():
        _, booking = completed()
    booking = close(booking)
    commission = commission_of(booking)
    ops = user_factory()

    def run(_):
        try:
            waive(commission, ops, 1_000)
            return "ok"
        except DomainError as exc:
            return exc.code
        finally:
            connection.close()

    with ThreadPoolExecutor(2) as pool:
        results = sorted(pool.map(run, [0, 1]))

    assert results == ["adjustment_exceeds_remaining", "ok"]
    assert provider_balance(commission.provider).due_xof == 500
