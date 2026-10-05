"""Données personnelles du portefeuille (spec 005, tâche 9) : bloqueur de suppression,
anonymiseur et purge des 4 derniers chiffres du payeur."""

import uuid
from datetime import timedelta

import pytest
from django.utils import timezone

from jeflink.accounts.deletion import _ANONYMIZERS, deletion_blockers
from jeflink.payments import services
from jeflink.payments.models import PaymentIntent, SettlementChannel
from jeflink.providers.tests.factories import VerifiedProviderFactory
from jeflink.trust.models import AuditEvent
from jeflink.wallet.selectors import provider_balance
from jeflink.wallet.services import post_goodwill_credit

from .test_settlements import owe

pytestmark = pytest.mark.django_db
BLOCKED = "deletion_blocked_wallet_balance"


@pytest.fixture
def provider():
    return VerifiedProviderFactory()


@pytest.fixture
def wave():
    return SettlementChannel.objects.create(
        slug="wave", gateway="manual_mobile_money", label_fr="Wave"
    )


def declare(provider, channel, *, amount=1_000, last4="0542"):
    return services.declare_settlement(
        provider=provider,
        actor=provider.owner,
        channel=channel,
        amount_xof=amount,
        reference=f"T_{uuid.uuid4().hex[:10].upper()}",
        paid_at=timezone.now(),
        payer_last4=last4,
        idempotency_key=uuid.uuid4().hex,
    ).intent


# --- Bloqueur de suppression -------------------------------------------------------------------


def test_un_gerant_sans_portefeuille_ou_solde_peut_supprimer_son_compte(provider, user_factory):
    assert BLOCKED not in deletion_blockers(provider.owner)
    assert BLOCKED not in deletion_blockers(user_factory())  # pas de fiche pro


def test_une_dette_bloque_la_suppression(provider):
    owe(provider, 1_500)
    assert BLOCKED in deletion_blockers(provider.owner)


def test_un_avoir_bloque_aussi_la_suppression(provider, user_factory):
    post_goodwill_credit(
        provider=provider, amount_xof=500, reason_code="goodwill",
        note="Geste après un incident de paiement.", operator=user_factory(), key="g-1",
    )  # fmt: skip
    assert provider_balance(provider).credit_xof == 500
    assert BLOCKED in deletion_blockers(provider.owner)


def test_une_declaration_en_attente_bloque_la_suppression(provider, wave, user_factory):
    owe(provider, 1_000)
    intent = declare(provider, wave)
    services.confirm_settlement(intent=intent, operator=user_factory(), received_xof=1_000)
    assert BLOCKED not in deletion_blockers(provider.owner)  # soldé, rien en attente

    owe(provider, 1_000)
    declare(provider, wave)
    assert BLOCKED in deletion_blockers(provider.owner)


# --- Anonymiseur et purge ----------------------------------------------------------------------


def test_l_anonymiseur_efface_les_chiffres_du_payeur_et_garde_la_comptabilite(provider, wave):
    owe(provider, 1_000)
    intent = declare(provider, wave)
    _ANONYMIZERS["payments"](provider.owner)

    intent.refresh_from_db()
    assert intent.payer_last4 == ""
    assert (intent.declared_xof, intent.reference) != (0, "")
    assert provider_balance(provider).due_xof == 1_000


def test_la_purge_efface_les_chiffres_douze_mois_apres_la_decision(provider, wave, user_factory):
    owe(provider, 3_000)
    ops = user_factory()
    old, recent, withdrawn = (declare(provider, wave) for _ in range(3))
    services.confirm_settlement(intent=old, operator=ops, received_xof=1_000)
    services.reject_settlement(intent=recent, operator=ops, reason="amount_mismatch", note="")
    services.cancel_settlement(intent=withdrawn, actor=provider.owner)
    year_ago = timezone.now() - timedelta(days=366)
    PaymentIntent.objects.filter(pk=old.pk).update(decided_at=year_ago)
    PaymentIntent.objects.filter(pk=withdrawn.pk).update(updated_at=year_ago)

    assert services.purge_payer_last4() == 2
    values = dict(PaymentIntent.objects.values_list("pk", "payer_last4"))
    assert (values[old.pk], values[recent.pk], values[withdrawn.pk]) == ("", "0542", "")
    event = AuditEvent.objects.get(action="payments.payer_last4.purged")
    assert event.metadata == {"count": 2}
    assert services.purge_payer_last4() == 0
