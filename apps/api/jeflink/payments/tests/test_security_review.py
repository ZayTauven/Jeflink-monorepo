"""Corrections de la revue sécurité de la spec 005 : retrait borné, perte et retour de la
confiance, canal de règlement, verrou du compte, reçu unique, compte du grand livre protégé,
requête sans session, clés sensibles des journaux."""

import logging
import uuid
from datetime import timedelta

import pytest
from django.core.exceptions import ValidationError
from django.db import DatabaseError, connection, transaction
from django.test import RequestFactory
from django.utils import timezone

from jeflink.accounts.admin_site import StepUpForm, admin_step_up_valid
from jeflink.common.errors import DomainError
from jeflink.common.pii import redact
from jeflink.payments import services
from jeflink.payments.models import PaymentIntent, SettlementChannel
from jeflink.providers.tests.factories import VerifiedProviderFactory
from jeflink.trust.models import AuditEvent
from jeflink.wallet.models import LedgerAccount
from jeflink.wallet.selectors import provider_wallet
from jeflink.wallet.services import post_goodwill_credit, reverse_settlement

from .test_settlements import code_of, declare, owe

pytestmark = pytest.mark.django_db
NOTE = "Règlement confirmé à tort, doublon du relevé."


@pytest.fixture
def provider():
    return VerifiedProviderFactory()


@pytest.fixture
def ops(user_factory):
    return user_factory()


@pytest.fixture
def wave():
    return SettlementChannel.objects.create(
        slug="wave", gateway="manual_mobile_money", label_fr="Wave"
    )


@pytest.fixture
def cash():
    return SettlementChannel.objects.create(slug="caisse", gateway="cash", label_fr="Bureau")


# --- Constat 1 : retirer pour redéclarer ne prolonge rien --------------------------------------


def test_le_retrait_n_est_permis_que_juste_apres_la_declaration(provider, wave, settings):
    settings.WALLET_SETTLEMENT_CANCEL_WINDOW = timedelta(minutes=30)
    owe(provider, 30_000)
    intent = declare(provider, wave, amount=30_000).intent
    assert services.can_cancel(intent)
    PaymentIntent.objects.filter(pk=intent.pk).update(
        created_at=timezone.now() - timedelta(minutes=31)
    )
    intent.refresh_from_db()
    assert not services.can_cancel(intent)
    assert code_of(services.cancel_settlement, intent=intent, actor=provider.owner) == (
        "settlement_not_cancellable"
    )
    assert PaymentIntent.objects.get(pk=intent.pk).status == "declared"


# --- Constat 2 : la confiance se perd et ne revient qu'avec un règlement entier ---------------


def test_une_confirmation_inferieure_au_declare_retire_la_confiance(provider, wave, ops):
    owe(provider, 30_000)
    inflated = declare(provider, wave, amount=10_000, reference="T_INFLATE01").intent
    services.confirm_settlement(intent=inflated, operator=ops, received_xof=100)
    declare(provider, wave, amount=10_000, reference="T_INFLATE02")
    assert provider_wallet(provider).pending_xof == 0
    assert services.distrusted_since(provider) is not None


def test_la_confiance_revient_avec_un_reglement_entier(provider, wave, ops):
    owe(provider, 30_000)
    bad = declare(provider, wave, amount=5_000, reference="T_BAD000001").intent
    services.reject_settlement(intent=bad, operator=ops, reason="not_found", note="")
    good = declare(provider, wave, amount=5_000, reference="T_GOOD00001").intent
    services.confirm_settlement(intent=good, operator=ops, received_xof=5_000)
    assert services.distrusted_since(provider) is None


def test_un_reglement_contre_passe_retire_la_confiance(provider, wave, ops):
    owe(provider, 30_000)
    intent = declare(provider, wave, amount=5_000, reference="T_WRONG0001").intent
    services.confirm_settlement(intent=intent, operator=ops, received_xof=5_000)
    reverse_settlement(
        intent=intent, reason_code="duplicate_settlement", note=NOTE, operator=ops, key="r-1"
    )
    declare(provider, wave, amount=5_000, reference="T_AFTER0001")
    assert provider_wallet(provider).pending_xof == 0


# --- Constat 3 et 10 : canal de règlement ------------------------------------------------------


def test_changer_le_numero_d_un_canal_est_audite_et_alerte(wave, ops, caplog):
    wave.account_display = "70 999 99 99"
    with caplog.at_level(logging.WARNING, logger="jeflink.alerts"):
        services.save_channel(channel=wave, operator=ops)
    event = AuditEvent.objects.get(action="payments.channel.saved")
    assert event.metadata["changed_fields"] == ["account_display"]
    assert "wallet_channel_account_changed" in caplog.text
    assert "70 999 99 99" not in str(event.metadata)


def test_un_canal_factice_est_refuse_hors_local_et_test(settings, ops):
    settings.DJANGO_ENV = "production"
    with pytest.raises(ValidationError):
        services.save_channel(
            channel=SettlementChannel(slug="factice", gateway="fake", label_fr="Factice"),
            operator=ops,
        )


# --- Constat 4 : les écritures de l'Ops sous le verrou du compte -------------------------------


def test_l_ops_n_ecrit_pas_sur_le_compte_d_un_gerant_supprime(provider, cash, ops):
    owner = provider.owner
    owner.is_active = False
    owner.deactivation_reason = "test"
    owner.save(update_fields=["is_active", "deactivation_reason"])
    assert code_of(
        services.record_cash_settlement,
        provider=provider,
        operator=ops,
        channel=cash,
        amount_xof=1_000,
        receipt_number="R-1",
        idempotency_key="c-1",
    ) == ("account_inactive")
    assert code_of(
        post_goodwill_credit,
        provider=provider,
        amount_xof=500,
        reason_code="goodwill",
        note="Geste commercial après incident.",
        operator=ops,
        key="g-1",
    ) == ("account_inactive")


# --- Constat 5 : un reçu ne sert qu'une fois ---------------------------------------------------


def test_un_recu_ne_s_enregistre_qu_une_fois_par_caisse(provider, cash, ops, user_factory):
    owe(provider, 5_000)
    services.record_cash_settlement(
        provider=provider, operator=ops, channel=cash, amount_xof=1_000,
        receipt_number="R-0042", idempotency_key="c-1",
    )  # fmt: skip
    assert code_of(
        services.record_cash_settlement,
        provider=provider,
        operator=user_factory(),
        channel=cash,
        amount_xof=1_000,
        receipt_number="R-0042",
        idempotency_key="c-2",
    ) == ("receipt_number_used")


# --- Constat 7 : compte du grand livre protégé -------------------------------------------------


def test_un_compte_du_grand_livre_ne_change_ni_de_pro_ni_de_type(provider):
    owe(provider, 1_000)
    account = LedgerAccount.objects.get(provider=provider)
    LedgerAccount.objects.filter(pk=account.pk).update(last_reminder_at=timezone.now())
    other = VerifiedProviderFactory()
    with pytest.raises(DatabaseError, match="relance"), transaction.atomic():
        LedgerAccount.objects.filter(pk=account.pk).update(provider=other)
    # SQL brut : Django refuse déjà la suppression (clé protégée), le trigger aussi.
    with (
        pytest.raises(DatabaseError, match="relance"),
        transaction.atomic(),
        connection.cursor() as cursor,
    ):
        cursor.execute("DELETE FROM wallet_ledgeraccount WHERE id = %s", [account.pk])


# --- Constats 8, 9, 12, 13 ---------------------------------------------------------------------


def test_sans_session_la_fenetre_est_fermee_sans_erreur():
    request = RequestFactory().post("/")
    assert admin_step_up_valid(request) is False
    form = StepUpForm(data={"otp_code": "123456"}, request=request)
    assert not form.is_valid()


def test_les_cles_des_reglements_sont_masquees_dans_les_journaux():
    text = redact("reference=T_8XQ4L2ZK9P payer_last4=0542 receipt_number=R-0042")
    assert "T_8XQ4L2ZK9P" not in text and "0542" not in text and "R-0042" not in text


def test_une_correction_reevalue_les_seuils(provider, wave, ops, settings, monkeypatch):
    from jeflink.notifications import events

    sent = []
    monkeypatch.setattr(events, "notify", lambda kind, recipients, ref: sent.append(kind))
    settings.WALLET_DEBT_ALERT_XOF = 10_000
    settings.WALLET_DEBT_BLOCK_XOF = 25_000
    owe(provider, 30_000)
    intent = declare(provider, wave, amount=10_000, reference="T_LOWER0001").intent
    services.request_correction(intent=intent, operator=ops, reason="amount_mismatch")
    sent.clear()
    services.correct_settlement(
        intent=intent,
        actor=provider.owner,
        amount_xof=1_000,
        reference="T_LOWER0002",
        paid_at=timezone.now(),
        payer_last4="",
    )
    assert events.WALLET_QUOTES_BLOCKED in sent


def test_un_rejeu_d_ajustement_sur_un_autre_pro_est_refuse(provider, ops):
    other = VerifiedProviderFactory()
    key = uuid.uuid4().hex
    common = {"amount_xof": 500, "reason_code": "goodwill", "note": NOTE, "operator": ops}
    post_goodwill_credit(provider=provider, key=key, **common)
    with pytest.raises(DomainError) as exc:
        post_goodwill_credit(provider=other, key=key, **common)
    assert exc.value.code == "idempotency_key_reused"
