"""Soldes du grand livre, toujours dérivés des lignes (aucun champ ``balance``, ADR 0012)."""

from dataclasses import dataclass

from django.db.models import BigIntegerField, Case, F, Q, Sum, When
from django.db.models.functions import Coalesce

from .models import (
    CREDIT_NORMAL_KINDS,
    AccountKind,
    CommissionRate,
    LedgerAccount,
    LedgerEntry,
    Side,
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
