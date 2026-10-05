"""Règlements de la commission (spec 005, tâche 5) : déclaration du pro, correction, retrait,
décisions de l'Ops, saisie directe depuis le relevé ou en espèces, effet sur la dette effective,
données personnelles."""

import logging
import re
import uuid
from datetime import timedelta

import pytest
from django.utils import timezone

from jeflink.common.errors import DomainError
from jeflink.common.ratelimit import Limit
from jeflink.notifications import events
from jeflink.payments import services
from jeflink.payments.models import PaymentIntent, SettlementChannel
from jeflink.providers.models import Provider
from jeflink.providers.tests.factories import VerifiedProviderFactory
from jeflink.trust.models import AuditEvent
from jeflink.wallet.models import LedgerTransaction
from jeflink.wallet.selectors import provider_balance, provider_wallet
from jeflink.wallet.services import Line, platform_account, post_transaction, provider_account

pytestmark = pytest.mark.django_db

REFERENCE = "T_8XQ4L2ZK9P"


@pytest.fixture
def provider():
    return VerifiedProviderFactory()


@pytest.fixture
def ops(user_factory):
    return user_factory()


@pytest.fixture
def wave():
    return SettlementChannel.objects.create(
        slug="wave", gateway="manual_mobile_money", label_fr="Wave", account_display="77 000 00 00"
    )


@pytest.fixture
def cash():
    return SettlementChannel.objects.create(slug="caisse", gateway="cash", label_fr="Bureau")


@pytest.fixture
def notified(monkeypatch):
    sent = []
    monkeypatch.setattr(
        events, "notify", lambda kind, recipients, ref: sent.append((kind, list(recipients), ref))
    )
    return sent


def owe(provider, amount):
    """Commission due par le pro (écrite comme à une clôture)."""
    post_transaction(
        kind="commission",
        lines=[
            Line(provider_account(provider), "debit", amount),
            Line(platform_account("platform_revenue"), "credit", amount),
        ],
        idempotency_key=f"commission:{uuid.uuid4()}",
        actor_kind="system",
        provider=provider,
    )


def key():
    return uuid.uuid4().hex


def declare(provider, channel, amount=4_500, reference=REFERENCE, **kwargs):
    params = {
        "provider": provider,
        "actor": provider.owner,
        "channel": channel,
        "amount_xof": amount,
        "reference": reference,
        "paid_at": timezone.now() - timedelta(minutes=10),
        "payer_last4": "",
        "idempotency_key": key(),
    } | kwargs
    return services.declare_settlement(**params)


def code_of(callable_, *args, **kwargs) -> str:
    with pytest.raises(DomainError) as exc:
        callable_(*args, **kwargs)
    return exc.value.code


# --- Déclaration -------------------------------------------------------------------------------


def test_le_pro_declare_un_reglement_qui_compte_comme_paye(provider, wave):
    owe(provider, 4_500)
    created = declare(provider, wave, reference="  t_8xq4 l2zk9p ")

    intent = created.intent
    assert created.created
    assert (intent.status, intent.origin, intent.declared_xof) == (
        "declared",
        "pro_declared",
        4_500,
    )
    assert intent.reference == REFERENCE  # espaces retirés, majuscules
    wallet = provider_wallet(provider)
    assert (wallet.due_xof, wallet.pending_xof, wallet.effective_due_xof) == (4_500, 4_500, 0)
    event = AuditEvent.objects.get(action="payments.settlement.declared")
    assert event.metadata == {"amount_xof": 4_500, "channel": "wave"}


def test_une_declaration_rejouee_ne_cree_rien_de_plus(provider, wave):
    owe(provider, 4_500)
    same = key()
    first = declare(provider, wave, idempotency_key=same, paid_at=timezone.now())
    again = services.declare_settlement(
        provider=provider,
        actor=provider.owner,
        channel=wave,
        amount_xof=4_500,
        reference=REFERENCE,
        paid_at=first.intent.paid_at,
        payer_last4="",
        idempotency_key=same,
    )
    assert (again.created, again.intent.pk) == (False, first.intent.pk)
    assert code_of(declare, provider, wave, amount=4_000, idempotency_key=same) == (
        "idempotency_key_reused"
    )


@pytest.mark.parametrize(
    "reference", ["T_8XQ4L2ZK9P", "MP231005.1234.A12345", "CI231005.1534.B56789", "8KD72PQ0"]
)
def test_les_references_reelles_sont_acceptees(reference):
    assert services.normalize_reference(reference) == reference


@pytest.mark.parametrize(
    "reference", ["", "ABC12", "771234567", "77 123 45 67", "+221771234567", "T_8XQ#4L2"]
)
def test_une_reference_invalide_ou_qui_ressemble_a_un_numero_est_refusee(reference):
    assert code_of(services.normalize_reference, reference) == "settlement_reference_invalid"


@pytest.mark.parametrize(
    ("kwargs", "code"),
    [
        ({"amount": 0}, "settlement_amount_invalid"),
        ({"amount": 4_500.0}, "settlement_amount_invalid"),
        ({"amount": 4_501}, "settlement_exceeds_due"),
        ({"payer_last4": "12a4"}, "payer_last4_invalid"),
        ({"payer_last4": "123"}, "payer_last4_invalid"),
        ({"paid_at": "future"}, "paid_at_invalid"),
        ({"paid_at": "old"}, "paid_at_invalid"),
    ],
)
def test_une_declaration_invalide_est_refusee(provider, wave, kwargs, code):
    owe(provider, 4_500)
    when = {
        "future": timezone.now() + timedelta(hours=1),
        "old": timezone.now() - timedelta(days=31),
    }
    if "paid_at" in kwargs:
        kwargs = {"paid_at": when[kwargs["paid_at"]]}
    assert code_of(declare, provider, wave, **kwargs) == code
    assert not PaymentIntent.objects.exists()


def test_le_montant_declare_ne_depasse_pas_ce_qui_reste_a_payer(provider, wave):
    owe(provider, 4_500)
    declare(provider, wave, amount=3_000)
    with pytest.raises(DomainError) as exc:
        declare(provider, wave, amount=2_000, reference="T_OTHER0001")
    assert (exc.value.code, exc.value.extra) == ("settlement_exceeds_due", {"payable_xof": 1_500})
    declare(provider, wave, amount=1_500, reference="T_OTHER0001")
    assert code_of(declare, provider, wave, amount=1, reference="T_OTHER0002") == "nothing_due"


def test_rien_a_payer(provider, wave):
    assert code_of(declare, provider, wave) == "nothing_due"


def test_les_especes_et_un_canal_inactif_ne_se_declarent_pas(provider, wave, cash):
    owe(provider, 4_500)
    assert code_of(declare, provider, cash) == "channel_inactive"
    wave.is_active = False
    wave.save()
    assert code_of(declare, provider, wave) == "channel_inactive"


def test_au_plus_trois_declarations_en_attente(provider, wave):
    owe(provider, 10_000)
    for n in range(3):
        declare(provider, wave, amount=1_000, reference=f"T_PENDING{n:03d}")
    assert code_of(declare, provider, wave, amount=1_000, reference="T_PENDING999") == (
        "settlement_pending_limit"
    )


def test_une_reference_ne_regle_qu_une_fois_par_canal(provider, wave):
    owe(provider, 9_000)
    declare(provider, wave)
    assert code_of(declare, provider, wave) == "settlement_reference_used"
    orange = SettlementChannel.objects.create(
        slug="orange-money", gateway="manual_mobile_money", label_fr="Orange Money"
    )
    declare(provider, orange)  # même référence, autre canal


def test_seul_le_gerant_declare(provider, wave, user_factory):
    owe(provider, 4_500)
    assert code_of(declare, provider, wave, actor=user_factory()) == "not_found"


def test_un_pro_suspendu_peut_regler_sa_dette(provider, wave):
    owe(provider, 4_500)
    Provider.objects.filter(pk=provider.pk).update(status=Provider.Status.SUSPENDED)
    provider.refresh_from_db()
    assert declare(provider, wave).created


def test_les_declarations_sont_limitees_par_jour(provider, wave, monkeypatch):
    owe(provider, 9_000)
    monkeypatch.setattr(services, "DECLARE_LIMIT", Limit("payments:declare:test", 1, 3600))
    declare(provider, wave, amount=1_000)
    assert code_of(declare, provider, wave, amount=1_000, reference="T_SECOND001") == (
        "settlement_rate_limited"
    )


def test_sans_redis_la_declaration_est_refusee(provider, wave, redis_down):
    owe(provider, 4_500)
    assert code_of(declare, provider, wave) == "settlement_rate_limited"


# --- Retrait et correction par le pro ----------------------------------------------------------


def test_le_pro_retire_une_declaration_en_attente(provider, wave):
    owe(provider, 4_500)
    intent = declare(provider, wave).intent
    services.cancel_settlement(intent=intent, actor=provider.owner)

    intent.refresh_from_db()
    assert intent.status == "cancelled"
    assert provider_wallet(provider).effective_due_xof == 4_500
    assert code_of(services.cancel_settlement, intent=intent, actor=provider.owner) == (
        "settlement_not_pending"
    )
    declare(provider, wave)  # la référence d'une déclaration retirée se libère


def test_un_autre_ne_retire_pas_la_declaration(provider, wave, user_factory):
    owe(provider, 4_500)
    intent = declare(provider, wave).intent
    assert code_of(services.cancel_settlement, intent=intent, actor=user_factory()) == "not_found"


def test_renvoi_a_corriger_puis_correction_une_seule_fois(provider, wave, ops, notified):
    owe(provider, 4_500)
    intent = declare(provider, wave, reference="T_TYPO00001").intent
    services.request_correction(intent=intent, operator=ops, reason="reference_not_found")

    intent.refresh_from_db()
    assert (intent.status, intent.correction_reason) == ("needs_correction", "reference_not_found")
    assert provider_wallet(provider).effective_due_xof == 0  # compte toujours comme payé
    assert (events.WALLET_SETTLEMENT_NEEDS_CORRECTION, [provider.owner], intent.public_id) in (
        notified
    )
    assert events.WALLET_SETTLEMENT_NEEDS_CORRECTION in events.SMS_KINDS

    services.correct_settlement(
        intent=intent,
        actor=provider.owner,
        amount_xof=4_500,
        reference=REFERENCE,
        paid_at=timezone.now(),
        payer_last4="0542",
    )
    intent.refresh_from_db()
    assert (intent.status, intent.reference, intent.payer_last4) == ("declared", REFERENCE, "0542")
    assert intent.corrected_at is not None
    assert code_of(
        services.request_correction, intent=intent, operator=ops, reason="amount_mismatch"
    ) == ("settlement_not_correctable")


def test_corriger_exige_un_renvoi(provider, wave):
    owe(provider, 4_500)
    intent = declare(provider, wave).intent
    assert code_of(
        services.correct_settlement,
        intent=intent,
        actor=provider.owner,
        amount_xof=4_500,
        reference=REFERENCE,
        paid_at=timezone.now(),
        payer_last4="",
    ) == ("settlement_not_correctable")


# --- Confirmation et rejet par l'Ops -----------------------------------------------------------


def test_l_ops_confirme_et_la_dette_baisse_au_grand_livre(provider, wave, ops, notified):
    owe(provider, 4_500)
    intent = declare(provider, wave).intent
    services.confirm_settlement(intent=intent, operator=ops, received_xof=4_500)

    intent.refresh_from_db()
    assert (intent.status, intent.received_xof, intent.decided_by) == ("confirmed", 4_500, ops)
    assert provider_balance(provider).due_xof == 0
    txn = LedgerTransaction.objects.get(kind="settlement")
    assert txn.payment_intent == intent and txn.actor == ops
    event = AuditEvent.objects.get(action="payments.settlement.confirmed")
    assert event.metadata["difference_xof"] == 0
    assert (events.WALLET_SETTLEMENT_CONFIRMED, [provider.owner], intent.public_id) in notified


def test_un_montant_recu_different_est_permis_et_audite(provider, wave, ops):
    owe(provider, 4_500)
    intent = declare(provider, wave).intent
    services.confirm_settlement(intent=intent, operator=ops, received_xof=4_000)

    assert provider_balance(provider).due_xof == 500
    event = AuditEvent.objects.get(action="payments.settlement.confirmed")
    assert (event.metadata["declared_xof"], event.metadata["difference_xof"]) == (4_500, -500)


def test_un_exces_recu_devient_un_avoir(provider, wave, ops):
    owe(provider, 4_500)
    intent = declare(provider, wave).intent
    services.confirm_settlement(intent=intent, operator=ops, received_xof=5_000)
    assert provider_balance(provider).credit_xof == 500


def test_l_ops_ne_decide_jamais_pour_son_propre_compte_pro(provider, wave):
    owe(provider, 4_500)
    intent = declare(provider, wave).intent
    owner = provider.owner
    assert code_of(
        services.confirm_settlement, intent=intent, operator=owner, received_xof=4_500
    ) == ("operator_is_provider")
    assert code_of(
        services.reject_settlement, intent=intent, operator=owner, reason="other", note=""
    ) == ("operator_is_provider")
    assert code_of(
        services.request_correction, intent=intent, operator=owner, reason="amount_mismatch"
    ) == ("operator_is_provider")


def test_une_confirmation_ne_s_ecrit_qu_une_fois(provider, wave, ops):
    owe(provider, 4_500)
    intent = declare(provider, wave).intent
    services.confirm_settlement(intent=intent, operator=ops, received_xof=4_500)
    assert code_of(
        services.confirm_settlement, intent=intent, operator=ops, received_xof=4_500
    ) == ("settlement_not_pending")
    assert LedgerTransaction.objects.filter(kind="settlement").count() == 1


def test_une_declaration_a_corriger_peut_etre_confirmee(provider, wave, ops):
    owe(provider, 4_500)
    intent = declare(provider, wave).intent
    services.request_correction(intent=intent, operator=ops, reason="paid_at_mismatch")
    services.confirm_settlement(intent=intent, operator=ops, received_xof=4_500)
    assert provider_balance(provider).due_xof == 0


def test_un_rejet_retire_l_effet_de_la_declaration(provider, wave, ops, notified):
    owe(provider, 4_500)
    intent = declare(provider, wave).intent
    services.reject_settlement(
        intent=intent, operator=ops, reason="amount_mismatch", note="Montant différent du relevé"
    )

    intent.refresh_from_db()
    assert (intent.status, intent.reject_reason) == ("rejected", "amount_mismatch")
    assert provider_wallet(provider).effective_due_xof == 4_500
    assert (events.WALLET_SETTLEMENT_REJECTED, [provider.owner], intent.public_id) in notified
    event = AuditEvent.objects.get(action="payments.settlement.rejected")
    assert event.metadata == {"reason": "amount_mismatch", "declared_xof": 4_500}


@pytest.mark.parametrize(
    ("reason", "note", "code"),
    [
        ("inconnu", "", "reject_reason_invalid"),
        ("other", "Appeler le 77 123 45 67", "note_invalid"),
    ],
)
def test_un_rejet_invalide_est_refuse(provider, wave, ops, reason, note, code):
    owe(provider, 4_500)
    intent = declare(provider, wave).intent
    assert (
        code_of(services.reject_settlement, intent=intent, operator=ops, reason=reason, note=note)
        == code
    )


def test_apres_un_rejet_introuvable_les_declarations_suivantes_ne_comptent_plus(
    provider, wave, ops
):
    owe(provider, 13_500)
    first = declare(provider, wave, amount=4_500, reference="T_FAKE00001").intent
    services.reject_settlement(intent=first, operator=ops, reason="not_found", note="")

    declare(provider, wave, amount=4_500, reference="T_FAKE00002")
    assert provider_wallet(provider).pending_xof == 0  # ne compte plus comme payée

    third = declare(provider, wave, amount=4_500, reference="T_REAL00003").intent
    services.confirm_settlement(intent=third, operator=ops, received_xof=4_500)
    # Une confirmation rétablit la confiance : les déclarations en attente comptent de nouveau.
    declare(provider, wave, amount=1_000, reference="T_REAL00004")
    assert provider_wallet(provider).pending_xof == 5_500


def test_un_rejet_pour_montant_ne_retire_pas_la_confiance(provider, wave, ops):
    owe(provider, 9_000)
    first = declare(provider, wave, amount=4_500, reference="T_AMOUNT001").intent
    services.reject_settlement(intent=first, operator=ops, reason="amount_mismatch", note="")
    declare(provider, wave, amount=4_500, reference="T_AMOUNT002")
    assert provider_wallet(provider).pending_xof == 4_500


# --- Saisie par l'Ops --------------------------------------------------------------------------


def test_l_ops_credite_un_versement_vu_dans_le_releve(provider, wave, ops, notified):
    owe(provider, 4_500)
    created = services.record_mobile_money_settlement(
        provider=provider,
        operator=ops,
        channel=wave,
        amount_xof=4_500,
        reference=REFERENCE,
        paid_at=timezone.now(),
        idempotency_key="ops-1",
    )
    intent = created.intent
    assert (intent.origin, intent.status, intent.received_xof) == (
        "ops_recorded",
        "confirmed",
        4_500,
    )
    assert provider_balance(provider).due_xof == 0
    # Le pro qui déclare ensuite la même transaction est arrêté.
    owe(provider, 1_000)
    assert code_of(declare, provider, wave, amount=1_000) == "settlement_reference_used"
    replay = services.record_mobile_money_settlement(
        provider=provider,
        operator=ops,
        channel=wave,
        amount_xof=4_500,
        reference=REFERENCE,
        paid_at=intent.paid_at,
        idempotency_key="ops-1",
    )
    assert (replay.created, replay.intent.pk) == (False, intent.pk)
    assert LedgerTransaction.objects.filter(kind="settlement").count() == 1


def test_l_ops_enregistre_des_especes_avec_un_recu(provider, wave, cash, ops):
    owe(provider, 4_500)
    created = services.record_cash_settlement(
        provider=provider,
        operator=ops,
        channel=cash,
        amount_xof=4_500,
        receipt_number="R-2026-0042",
        idempotency_key="cash-1",
    )
    assert (created.intent.gateway, created.intent.receipt_number) == ("cash", "R-2026-0042")
    assert provider_balance(provider).due_xof == 0
    assert code_of(
        services.record_cash_settlement,
        provider=provider,
        operator=ops,
        channel=wave,
        amount_xof=1_000,
        receipt_number="R-1",
        idempotency_key="cash-2",
    ) == ("channel_inactive")
    assert code_of(
        services.record_cash_settlement,
        provider=provider,
        operator=ops,
        channel=cash,
        amount_xof=1_000,
        receipt_number="77 123 45 67",
        idempotency_key="cash-3",
    ) == ("receipt_number_invalid")


def test_l_ops_ne_saisit_pas_pour_son_propre_compte(provider, cash):
    assert code_of(
        services.record_cash_settlement,
        provider=provider,
        operator=provider.owner,
        channel=cash,
        amount_xof=1_000,
        receipt_number="R-1",
        idempotency_key="cash-own",
    ) == ("operator_is_provider")


# --- Seuils ------------------------------------------------------------------------------------


def test_declarer_leve_le_blocage_et_un_rejet_le_retablit(provider, wave, ops, settings, notified):
    settings.WALLET_DEBT_ALERT_XOF = 10_000
    settings.WALLET_DEBT_BLOCK_XOF = 25_000
    owe(provider, 30_000)
    assert provider_wallet(provider).state == "blocked"

    intent = declare(provider, wave, amount=10_000).intent
    assert provider_wallet(provider).state == "alert"
    assert notified[-1] == (events.WALLET_QUOTES_UNBLOCKED, [provider.owner], provider.public_id)

    services.reject_settlement(intent=intent, operator=ops, reason="not_found", note="")
    assert provider_wallet(provider).state == "blocked"
    assert notified[-1] == (events.WALLET_QUOTES_BLOCKED, [provider.owner], provider.public_id)


def test_une_declaration_ancienne_compte_tant_que_l_ops_n_a_pas_decide(provider, wave):
    owe(provider, 4_500)
    intent = declare(provider, wave).intent
    PaymentIntent.objects.filter(pk=intent.pk).update(
        created_at=timezone.now() - timedelta(days=10)
    )
    assert provider_wallet(provider).pending_xof == 4_500


# --- Surveillance et données personnelles ------------------------------------------------------


def test_watch_settlements_alerte_sur_les_declarations_en_retard(provider, wave, caplog):
    owe(provider, 9_000)
    late = declare(provider, wave, amount=4_500).intent
    declare(provider, wave, amount=4_500, reference="T_RECENT001")
    PaymentIntent.objects.filter(pk=late.pk).update(created_at=timezone.now() - timedelta(hours=25))
    with caplog.at_level(logging.WARNING, logger="jeflink.alerts"):
        assert services.watch_settlements() == 1
    assert "wallet_settlements_overdue" in caplog.text


def test_ni_la_reference_ni_les_chiffres_du_payeur_ne_sortent(provider, wave, ops, caplog):
    owe(provider, 4_500)
    with caplog.at_level(logging.DEBUG):
        intent = declare(provider, wave, payer_last4="0542").intent
        services.request_correction(intent=intent, operator=ops, reason="reference_not_found")
        services.correct_settlement(
            intent=intent,
            actor=provider.owner,
            amount_xof=4_500,
            reference="T_FIXED00001",
            paid_at=timezone.now(),
            payer_last4="0542",
        )
        services.confirm_settlement(intent=intent, operator=ops, received_xof=4_500)
    traces = caplog.text + "".join(str(e.metadata) for e in AuditEvent.objects.all())
    # Les UUID (public_id) peuvent contenir « 0542 » par hasard : on les retire d'abord.
    traces = re.sub(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", "", traces)
    for secret in (REFERENCE, "T_FIXED00001", "0542"):
        assert secret not in traces
