"""Écrivain unique du grand livre, contre-passation et soldes (spec 005, tâche 1)."""

import random
from decimal import Decimal

import pytest

from jeflink.providers.tests.factories import ProviderFactory
from jeflink.wallet.models import (
    AccountKind,
    ActorKind,
    LedgerAccount,
    LedgerEntry,
    LedgerTransaction,
    Side,
    TransactionKind,
)
from jeflink.wallet.selectors import balance, provider_balance
from jeflink.wallet.services import (
    LedgerError,
    Line,
    platform_account,
    post_transaction,
    provider_account,
    reverse,
    reversed_total,
)

pytestmark = pytest.mark.django_db

SHAPE = {
    TransactionKind.COMMISSION: (AccountKind.PRO_COMMISSION_DUE, AccountKind.PLATFORM_REVENUE),
    TransactionKind.SETTLEMENT: (AccountKind.PLATFORM_COLLECTIONS, AccountKind.PRO_COMMISSION_DUE),
    TransactionKind.GOODWILL_CREDIT: (
        AccountKind.PLATFORM_GOODWILL,
        AccountKind.PRO_COMMISSION_DUE,
    ),
    TransactionKind.CORRECTION_DEBIT: (
        AccountKind.PRO_COMMISSION_DUE,
        AccountKind.PLATFORM_REVENUE,
    ),
}


def account(provider, kind):
    return provider_account(provider, kind) if kind.startswith("pro_") else platform_account(kind)


def post(provider, kind, amount, key, **kwargs):
    debited, credited = SHAPE[kind]
    return post_transaction(
        kind=kind,
        lines=[
            Line(account(provider, debited), Side.DEBIT, amount),
            Line(account(provider, credited), Side.CREDIT, amount),
        ],
        idempotency_key=key,
        actor_kind=ActorKind.SYSTEM,
        provider=provider,
        **kwargs,
    )


@pytest.fixture
def provider():
    return ProviderFactory()


@pytest.fixture
def ops(user_factory):
    return user_factory()


# --- Écriture ----------------------------------------------------------------------------------


def test_une_commission_cree_la_dette_du_pro_et_le_revenu(provider):
    txn = post(provider, TransactionKind.COMMISSION, 3_000, "commission:1")

    assert txn.entries.count() == 2
    assert provider_balance(provider).due_xof == 3_000
    assert balance(platform_account(AccountKind.PLATFORM_REVENUE)) == 3_000
    assert balance(provider_account(provider)) == 3_000


def test_le_compte_du_pro_nait_au_premier_mouvement(provider):
    assert not LedgerAccount.objects.filter(provider=provider).exists()
    assert provider_balance(provider).due_xof == 0
    post(provider, TransactionKind.COMMISSION, 500, "commission:2")
    assert LedgerAccount.objects.filter(provider=provider).count() == 1


@pytest.mark.parametrize("amount", [1.0, Decimal(1000), True, 0, -5, "1000", None])
def test_un_montant_qui_n_est_pas_un_entier_positif_est_refuse(provider, amount):
    with pytest.raises(LedgerError):
        post(provider, TransactionKind.COMMISSION, amount, "commission:x")
    assert not LedgerTransaction.objects.exists()


def test_une_transaction_desequilibree_est_refusee(provider):
    with pytest.raises(LedgerError, match="déséquilibrée"):
        post_transaction(
            kind=TransactionKind.COMMISSION,
            lines=[
                Line(provider_account(provider), Side.DEBIT, 1_000),
                Line(platform_account(AccountKind.PLATFORM_REVENUE), Side.CREDIT, 999),
            ],
            idempotency_key="k",
            actor_kind=ActorKind.SYSTEM,
            provider=provider,
        )


def test_une_transaction_a_une_seule_ligne_est_refusee(provider):
    with pytest.raises(LedgerError, match="deux lignes"):
        post_transaction(
            kind=TransactionKind.COMMISSION,
            lines=[Line(provider_account(provider), Side.DEBIT, 1_000)],
            idempotency_key="k",
            actor_kind=ActorKind.SYSTEM,
            provider=provider,
        )


@pytest.mark.parametrize(
    "kind", [AccountKind.CLIENT_ESCROW, AccountKind.PRO_PENDING, AccountKind.PRO_AVAILABLE]
)
def test_aucune_ecriture_sur_les_comptes_de_la_v2(provider, kind):
    v2 = LedgerAccount.objects.create(
        kind=kind, provider=provider if kind.startswith("pro_") else None
    )
    with pytest.raises(LedgerError, match="hors V1"):
        post_transaction(
            kind=TransactionKind.COMMISSION,
            lines=[
                Line(v2, Side.DEBIT, 1_000),
                Line(platform_account(AccountKind.PLATFORM_REVENUE), Side.CREDIT, 1_000),
            ],
            idempotency_key="k",
            actor_kind=ActorKind.SYSTEM,
            provider=provider,
        )


def test_un_mouvement_hors_de_sa_forme_est_refuse(provider):
    """Une commission ne crédite jamais le compte du pro (ce serait un avoir déguisé)."""
    with pytest.raises(LedgerError, match="attendu"):
        post_transaction(
            kind=TransactionKind.COMMISSION,
            lines=[
                Line(platform_account(AccountKind.PLATFORM_REVENUE), Side.DEBIT, 1_000),
                Line(provider_account(provider), Side.CREDIT, 1_000),
            ],
            idempotency_key="k",
            actor_kind=ActorKind.SYSTEM,
            provider=provider,
        )


def test_le_compte_d_un_autre_pro_est_refuse(provider):
    other = ProviderFactory()
    with pytest.raises(LedgerError, match="autre pro"):
        post_transaction(
            kind=TransactionKind.COMMISSION,
            lines=[
                Line(provider_account(other), Side.DEBIT, 1_000),
                Line(platform_account(AccountKind.PLATFORM_REVENUE), Side.CREDIT, 1_000),
            ],
            idempotency_key="k",
            actor_kind=ActorKind.SYSTEM,
            provider=provider,
        )


def test_une_note_avec_un_numero_est_refusee(provider, ops):
    with pytest.raises(LedgerError, match="note"):
        post(
            provider,
            TransactionKind.GOODWILL_CREDIT,
            500,
            "goodwill:1",
            note="rappeler au 77 123 45 67",
        )


def test_l_acteur_doit_correspondre_a_son_type(provider, ops):
    with pytest.raises(LedgerError, match="acteur"):
        post_transaction(
            kind=TransactionKind.GOODWILL_CREDIT,
            lines=[
                Line(platform_account(AccountKind.PLATFORM_GOODWILL), Side.DEBIT, 500),
                Line(provider_account(provider), Side.CREDIT, 500),
            ],
            idempotency_key="goodwill:2",
            actor_kind=ActorKind.OPS,
            provider=provider,
        )


def test_les_comptes_de_pro_et_de_plateforme_ne_se_confondent_pas(provider):
    with pytest.raises(LedgerError):
        provider_account(provider, AccountKind.PLATFORM_REVENUE)
    with pytest.raises(LedgerError):
        platform_account(AccountKind.PRO_COMMISSION_DUE)


# --- Idempotence -------------------------------------------------------------------------------


def test_une_cle_rejouee_avec_le_meme_contenu_rend_la_meme_transaction(provider):
    first = post(provider, TransactionKind.COMMISSION, 2_000, "commission:9")
    again = post(provider, TransactionKind.COMMISSION, 2_000, "commission:9")

    assert again.pk == first.pk
    assert LedgerEntry.objects.count() == 2
    assert provider_balance(provider).due_xof == 2_000


def test_une_cle_rejouee_avec_un_autre_contenu_est_un_bug(provider):
    post(provider, TransactionKind.COMMISSION, 2_000, "commission:9")
    with pytest.raises(LedgerError, match="idempotence"):
        post(provider, TransactionKind.COMMISSION, 2_500, "commission:9")


# --- Contre-passation --------------------------------------------------------------------------


def test_une_contre_passation_totale_annule_la_commission(provider, ops):
    txn = post(provider, TransactionKind.COMMISSION, 3_000, "commission:1")
    rev = reverse(
        original=txn,
        amount_xof=3_000,
        idempotency_key="reversal:a",
        reason_code="entry_error",
        note="Mission saisie deux fois",
        actor=ops,
    )

    assert rev.kind == TransactionKind.REVERSAL
    assert rev.reverses_id == txn.pk
    assert provider_balance(provider).due_xof == 0
    assert balance(platform_account(AccountKind.PLATFORM_REVENUE)) == 0


def test_une_contre_passation_partielle_ne_depasse_jamais_le_montant(provider, ops):
    txn = post(provider, TransactionKind.COMMISSION, 3_000, "commission:1")
    common = {"reason_code": "dispute_refund", "note": "", "actor": ops}
    reverse(original=txn, amount_xof=1_000, idempotency_key="reversal:a", **common)
    reverse(original=txn, amount_xof=1_500, idempotency_key="reversal:b", **common)

    with pytest.raises(LedgerError, match="restant"):
        reverse(original=txn, amount_xof=501, idempotency_key="reversal:c", **common)
    assert reversed_total(txn) == 2_500
    assert provider_balance(provider).due_xof == 500


def test_une_contre_passation_rejouee_ne_s_ajoute_pas(provider, ops):
    txn = post(provider, TransactionKind.COMMISSION, 3_000, "commission:1")
    common = {"reason_code": "entry_error", "note": "", "actor": ops}
    first = reverse(original=txn, amount_xof=3_000, idempotency_key="reversal:a", **common)
    again = reverse(original=txn, amount_xof=3_000, idempotency_key="reversal:a", **common)

    assert again.pk == first.pk
    assert provider_balance(provider).due_xof == 0


def test_une_contre_passation_ne_se_contre_passe_pas(provider, ops):
    txn = post(provider, TransactionKind.COMMISSION, 3_000, "commission:1")
    common = {"reason_code": "entry_error", "note": "", "actor": ops}
    rev = reverse(original=txn, amount_xof=3_000, idempotency_key="reversal:a", **common)
    with pytest.raises(LedgerError):
        reverse(original=rev, amount_xof=3_000, idempotency_key="reversal:b", **common)


def test_la_contre_passation_d_un_reglement_recree_la_dette(provider, ops):
    post(provider, TransactionKind.COMMISSION, 3_000, "commission:1")
    settlement = post(provider, TransactionKind.SETTLEMENT, 3_000, "settlement:1")
    assert provider_balance(provider).due_xof == 0

    reverse(
        original=settlement,
        amount_xof=3_000,
        idempotency_key="reversal:a",
        reason_code="duplicate_settlement",
        note="",
        actor=ops,
    )
    assert provider_balance(provider).due_xof == 3_000
    assert balance(platform_account(AccountKind.PLATFORM_COLLECTIONS)) == 0


def test_un_trop_percu_devient_un_avoir(provider):
    post(provider, TransactionKind.COMMISSION, 3_000, "commission:1")
    post(provider, TransactionKind.SETTLEMENT, 5_000, "settlement:1")

    assert provider_balance(provider).due_xof == 0
    assert provider_balance(provider).credit_xof == 2_000


# --- Propriété : suites aléatoires -------------------------------------------------------------


@pytest.mark.parametrize("seed", range(5))
def test_le_grand_livre_reste_equilibre_sur_des_suites_aleatoires(seed, ops):
    """Somme de tous les comptes nulle ; solde du pro = commissions - règlements + corrections
    - gestes, chaque contre-passation jouant à l'inverse de ce qu'elle annule."""
    rng = random.Random(seed)  # noqa: S311 (suite reproductible, rien de cryptographique)
    providers = [ProviderFactory() for _ in range(3)]
    expected = dict.fromkeys(providers, 0)
    effect = {
        TransactionKind.COMMISSION: 1,
        TransactionKind.CORRECTION_DEBIT: 1,
        TransactionKind.SETTLEMENT: -1,
        TransactionKind.GOODWILL_CREDIT: -1,
    }
    reversible = []
    for step in range(60):
        provider = rng.choice(providers)
        if reversible and rng.random() < 0.2:
            txn, remaining = reversible.pop(rng.randrange(len(reversible)))
            amount = rng.randint(1, remaining)
            reverse(
                original=txn,
                amount_xof=amount,
                idempotency_key=f"reversal:{seed}:{step}",
                reason_code="other",
                note="",
                actor=ops,
            )
            expected[txn.provider] -= effect[txn.kind] * amount
            if remaining - amount:
                reversible.append((txn, remaining - amount))
            continue
        kind = rng.choice(list(effect))
        amount = rng.randint(1, 50_000)
        txn = post(provider, kind, amount, f"{kind}:{seed}:{step}")
        expected[provider] += effect[kind] * amount
        reversible.append((txn, amount))

    debits = sum(e.amount_xof for e in LedgerEntry.objects.filter(side=Side.DEBIT))
    credits = sum(e.amount_xof for e in LedgerEntry.objects.filter(side=Side.CREDIT))
    assert debits == credits
    for provider, net in expected.items():
        wallet = provider_balance(provider)
        assert wallet.due_xof - wallet.credit_xof == net
        assert all(type(v) is int for v in (wallet.due_xof, wallet.credit_xof))
