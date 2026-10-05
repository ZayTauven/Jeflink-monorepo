"""Soldes du grand livre, toujours dérivés des lignes (aucun champ ``balance``, ADR 0012)."""

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum

from django.conf import settings
from django.db.models import BigIntegerField, Case, F, Q, Sum, When
from django.db.models.functions import Coalesce

from jeflink.common.errors import DomainError

from .models import (
    CREDIT_NORMAL_KINDS,
    AccountKind,
    Commission,
    CommissionRate,
    LedgerAccount,
    LedgerEntry,
    LedgerTransaction,
    Side,
    TransactionKind,
)


def _signed_sum(queryset) -> int:
    """Débits moins crédits, en une agrégation."""
    signed = Case(
        When(side=Side.DEBIT, then=F("amount_xof")),
        default=-F("amount_xof"),
        output_field=BigIntegerField(),
    )
    return queryset.aggregate(net=Coalesce(Sum(signed), 0))["net"]


def balance(account: LedgerAccount) -> int:
    """Solde d'un compte dans son sens normal (positif : le compte « porte » ce montant)."""
    net = _signed_sum(LedgerEntry.objects.filter(account=account))
    return -net if account.kind in CREDIT_NORMAL_KINDS else net


@dataclass(frozen=True)
class ProviderBalance:
    due_xof: int  # le pro doit ce montant à Jeflink
    credit_xof: int  # avoir du pro (trop-perçu, geste commercial)


def provider_balance(provider) -> ProviderBalance:
    net = _signed_sum(
        LedgerEntry.objects.filter(
            account__provider=provider, account__kind=AccountKind.PRO_COMMISSION_DUE
        )
    )
    return ProviderBalance(due_xof=max(net, 0), credit_xof=max(-net, 0))


# Montant des règlements déclarés qui comptent comme payés (spec 005) : ``payments`` s'inscrit
# ici, ``wallet`` n'importe jamais ``payments`` (ADR 0012). Sans source : 0.
PendingSource = Callable[[object], int]
_PENDING_SOURCES: list[PendingSource] = []


def register_pending_source(source: PendingSource) -> None:
    if source not in _PENDING_SOURCES:
        _PENDING_SOURCES.append(source)


class WalletState(StrEnum):
    OK = "ok"
    ALERT = "alert"  # alerte envoyée au pro
    BLOCKED = "blocked"  # nouveaux devis refusés


@dataclass(frozen=True)
class ProviderWallet:
    due_xof: int
    credit_xof: int
    pending_xof: int  # déclarations qui comptent comme payées, plafonnées au dû
    effective_due_xof: int
    state: WalletState


def state_for(effective_due_xof: int) -> WalletState:
    if effective_due_xof >= settings.WALLET_DEBT_BLOCK_XOF:
        return WalletState.BLOCKED
    if effective_due_xof >= settings.WALLET_DEBT_ALERT_XOF:
        return WalletState.ALERT
    return WalletState.OK


def provider_wallet(provider) -> ProviderWallet:
    balance_now = provider_balance(provider)
    pending = min(sum(source(provider) for source in _PENDING_SOURCES), balance_now.due_xof)
    effective = balance_now.due_xof - pending
    return ProviderWallet(
        due_xof=balance_now.due_xof,
        credit_xof=balance_now.credit_xof,
        pending_xof=pending,
        effective_due_xof=effective,
        state=state_for(effective),
    )


def rate_for(*, trade, at) -> CommissionRate | None:
    """Taux applicable à un devis envoyé à ``at`` : celui du métier en vigueur à cette date,
    sinon le taux par défaut en vigueur à cette date. Un taux de métier, une fois en vigueur,
    prime sur tout taux par défaut, même plus récent."""
    in_force = CommissionRate.objects.filter(valid_from__lte=at).order_by("-valid_from")
    if trade is not None and (own := in_force.filter(trade=trade).first()) is not None:
        return own
    return in_force.filter(trade__isnull=True).first()


def next_rate_for(*, trade, at) -> CommissionRate | None:
    """Prochain taux annoncé (date d'effet après ``at``) qui s'appliquera à ce métier."""
    upcoming = CommissionRate.objects.filter(valid_from__gt=at).order_by("valid_from")
    if trade is not None:
        upcoming = upcoming.filter(Q(trade=trade) | Q(trade__isnull=True))
        if not CommissionRate.objects.filter(trade=trade, valid_from__lte=at).exists():
            return upcoming.first()
        # Le métier a son propre taux : seul un nouveau taux du métier le remplace.
        return upcoming.filter(trade=trade).first()
    return upcoming.filter(trade__isnull=True).first()


# --- Lectures du pro (API, spec 005 tâche 8) ---------------------------------------------------


def entries_for_provider(provider):
    """Lignes du compte de dette du pro, plus récentes d'abord : une par mouvement."""
    return (
        LedgerEntry.objects.filter(
            account__provider=provider, account__kind=AccountKind.PRO_COMMISSION_DUE
        )
        .select_related("transaction__booking__request__trade")
        .order_by("-created_at", "-id")
    )


def entry_for_provider(*, provider, public_id) -> LedgerEntry:
    """Ligne d'un mouvement du pro ; celui d'un autre pro répond ``not_found``."""
    entry = entries_for_provider(provider).filter(transaction__public_id=public_id).first()
    if entry is None:
        raise DomainError("not_found", status=404)
    return entry


def commission_for_transaction(transaction) -> Commission | None:
    return Commission.objects.filter(ledger_transaction=transaction).first()


def reversals_of(transaction):
    return transaction.reversals.order_by("created_at")


def settlement_reversals(provider) -> dict:
    """Règlements contre-passés du pro : ``{id de l'intention : date de la contre-passation}``
    (``payments`` en déduit la perte de confiance, sans importer le grand livre)."""
    rows = LedgerTransaction.objects.filter(
        provider=provider,
        kind=TransactionKind.REVERSAL,
        reverses__kind=TransactionKind.SETTLEMENT,
    ).values_list("reverses__payment_intent_id", "created_at")
    reversals: dict = {}
    for intent_id, created_at in rows:
        reversals[intent_id] = max(created_at, reversals.get(intent_id, created_at))
    return reversals
