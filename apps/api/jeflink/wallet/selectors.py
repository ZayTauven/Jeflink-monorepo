"""Soldes du grand livre, toujours dérivés des lignes (aucun champ ``balance``, ADR 0012)."""

from dataclasses import dataclass

from django.db.models import BigIntegerField, Case, F, Sum, When
from django.db.models.functions import Coalesce

from .models import CREDIT_NORMAL_KINDS, AccountKind, LedgerAccount, LedgerEntry, Side


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
