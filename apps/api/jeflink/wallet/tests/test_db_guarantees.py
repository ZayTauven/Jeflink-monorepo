"""Garanties du grand livre en base (migration 0002) : immuabilité et équilibre au commit, même
pour une écriture qui contourne ``post_transaction``. En transaction réelle : le trigger
d'équilibre est différé au commit."""

import pytest
from django.db import DatabaseError, connection, transaction

from jeflink.providers.tests.factories import ProviderFactory
from jeflink.wallet.models import (
    AccountKind,
    ActorKind,
    LedgerEntry,
    LedgerTransaction,
    Side,
    TransactionKind,
)
from jeflink.wallet.services import Line, platform_account, post_transaction, provider_account

pytestmark = pytest.mark.django_db(transaction=True, serialized_rollback=True)


def commission(provider, amount=1_000, key="commission:1"):
    return post_transaction(
        kind=TransactionKind.COMMISSION,
        lines=[
            Line(provider_account(provider), Side.DEBIT, amount),
            Line(platform_account(AccountKind.PLATFORM_REVENUE), Side.CREDIT, amount),
        ],
        idempotency_key=key,
        actor_kind=ActorKind.SYSTEM,
        provider=provider,
    )


def test_une_ligne_ne_se_modifie_ni_ne_se_supprime():
    txn = commission(ProviderFactory())
    entry = txn.entries.first()

    with pytest.raises(DatabaseError, match="immuable"):
        LedgerEntry.objects.filter(pk=entry.pk).update(amount_xof=1)
    with pytest.raises(DatabaseError, match="immuable"), transaction.atomic():
        entry.delete()
    assert LedgerEntry.objects.get(pk=entry.pk).amount_xof == 1_000


def test_une_transaction_ne_se_modifie_ni_ne_se_supprime():
    txn = commission(ProviderFactory())

    with pytest.raises(DatabaseError, match="immuable"):
        LedgerTransaction.objects.filter(pk=txn.pk).update(reason_code="x")
    with pytest.raises(DatabaseError, match="immuable"), connection.cursor() as cursor:
        cursor.execute("DELETE FROM wallet_ledgertransaction WHERE id = %s", [txn.pk])


def test_une_transaction_desequilibree_ecrite_en_sql_brut_est_refusee_au_commit():
    provider = ProviderFactory()
    due = provider_account(provider)
    revenue = platform_account(AccountKind.PLATFORM_REVENUE)

    with pytest.raises(DatabaseError, match="invalide"), transaction.atomic():
        txn = LedgerTransaction.objects.create(
            kind=TransactionKind.COMMISSION,
            idempotency_key="brut:1",
            provider=provider,
            actor_kind=ActorKind.SYSTEM,
        )
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO wallet_ledgerentry"
                " (transaction_id, account_id, side, amount_xof, created_at)"
                " VALUES (%s, %s, 'debit', 1000, now()), (%s, %s, 'credit', 999, now())",
                [txn.pk, due.pk, txn.pk, revenue.pk],
            )
    assert not LedgerTransaction.objects.filter(idempotency_key="brut:1").exists()


def test_une_transaction_sans_ligne_est_refusee_au_commit():
    provider = ProviderFactory()
    with pytest.raises(DatabaseError, match="invalide"), transaction.atomic():
        LedgerTransaction.objects.create(
            kind=TransactionKind.COMMISSION,
            idempotency_key="vide:1",
            provider=provider,
            actor_kind=ActorKind.SYSTEM,
        )
    assert not LedgerTransaction.objects.exists()


def test_une_ligne_ajoutee_seule_a_une_transaction_passee_est_refusee():
    txn = commission(ProviderFactory())
    with pytest.raises(DatabaseError, match="invalide"), transaction.atomic():
        LedgerEntry.objects.create(
            transaction=txn,
            account=platform_account(AccountKind.PLATFORM_REVENUE),
            side=Side.CREDIT,
            amount_xof=1,
        )
    assert txn.entries.count() == 2


def test_une_transaction_equilibree_passe_le_commit():
    provider = ProviderFactory()
    with transaction.atomic():
        commission(provider, 2_000, "commission:a")
        commission(provider, 3_000, "commission:b")
    assert LedgerTransaction.objects.count() == 2
