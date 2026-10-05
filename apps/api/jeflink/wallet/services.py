"""Écritures du grand livre (spec 005, ADR 0012).

``post_transaction`` est le seul écrivain de ``LedgerTransaction`` et ``LedgerEntry`` (test
d'architecture) ; les services métier (commission, règlement, ajustements) l'appellent. Une
incohérence de montant ou de compte est un bug de l'appelant : ``LedgerError`` (``ValueError``),
jamais une erreur montrée à un utilisateur.

Ordre des verrous (prolongé, ADR 0012) : comptes utilisateurs (par id), fiche pro, demande,
réservation, intention de paiement, comptes du grand livre du pro (par id). Les comptes de la
plateforme ne sont jamais verrouillés.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from django.db import IntegrityError, connection, transaction
from django.db.models import Sum

from jeflink.common.pii import contains_pii

from .models import (
    PROVIDER_ACCOUNT_KINDS,
    V1_ACCOUNT_KINDS,
    AccountKind,
    ActorKind,
    LedgerAccount,
    LedgerEntry,
    LedgerTransaction,
    Side,
    TransactionKind,
)

# Forme de chaque mouvement de la V1 : (compte débité, compte crédité). Une contre-passation
# prend la forme inverse de la transaction qu'elle annule.
SHAPES: dict[str, tuple[str, str]] = {
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

# Triggers de contrainte différés de la migration 0002 (équilibre et au moins deux lignes).
BALANCE_TRIGGERS = "wallet_ledgerentry_balanced, wallet_ledgertransaction_balanced"


class LedgerError(ValueError):
    """Écriture refusée : bug de l'appelant, jamais une erreur d'utilisateur."""


@dataclass(frozen=True)
class Line:
    account: LedgerAccount
    side: str
    amount_xof: int


# --- Comptes -----------------------------------------------------------------------------------


def provider_account(provider, kind: str = AccountKind.PRO_COMMISSION_DUE) -> LedgerAccount:
    """Compte d'un pro, créé à son premier mouvement. L'appelant tient le verrou de la fiche."""
    if kind not in PROVIDER_ACCOUNT_KINDS:
        raise LedgerError(f"compte de plateforme demandé pour un pro : {kind}")
    account, _ = LedgerAccount.objects.get_or_create(kind=kind, provider=provider)
    return account


def platform_account(kind: str) -> LedgerAccount:
    """Compte de la plateforme (créé par migration ; recréé à la demande après un flush)."""
    if kind in PROVIDER_ACCOUNT_KINDS:
        raise LedgerError(f"compte de pro demandé pour la plateforme : {kind}")
    account, _ = LedgerAccount.objects.get_or_create(kind=kind, provider=None)
    return account


def _lock_provider_accounts(accounts: Sequence[LedgerAccount]) -> None:
    ids = sorted({a.pk for a in accounts if a.kind in PROVIDER_ACCOUNT_KINDS})
    if ids:
        list(LedgerAccount.objects.select_for_update().filter(pk__in=ids).order_by("pk"))


# --- Écrivain unique ---------------------------------------------------------------------------


def _check_amount(amount_xof: object) -> int:
    # ``bool`` est un ``int`` en Python : refusé explicitement, comme float et Decimal.
    if type(amount_xof) is not int or amount_xof <= 0:
        raise LedgerError("montant invalide : entier XOF strictement positif attendu")
    return amount_xof


def _check_lines(
    *, kind: str, lines: Sequence[Line], provider, reverses: LedgerTransaction | None
) -> None:
    if len(lines) < 2:
        raise LedgerError("une transaction a au moins deux lignes")
    debit = credit = 0
    for line in lines:
        amount = _check_amount(line.amount_xof)
        if line.side == Side.DEBIT:
            debit += amount
        elif line.side == Side.CREDIT:
            credit += amount
        else:
            raise LedgerError(f"côté inconnu : {line.side}")
        if line.account.kind not in V1_ACCOUNT_KINDS:
            raise LedgerError(f"compte hors V1 : {line.account.kind}")
        if line.account.kind in PROVIDER_ACCOUNT_KINDS and (
            provider is None or line.account.provider_id != provider.pk
        ):
            raise LedgerError("compte d'un autre pro que celui de la transaction")
    if debit != credit:
        raise LedgerError("transaction déséquilibrée")

    if kind == TransactionKind.REVERSAL:
        if reverses is None or reverses.kind == TransactionKind.REVERSAL:
            raise LedgerError("une contre-passation annule une transaction qui n'en est pas une")
        credited, debited = SHAPES[reverses.kind]
    elif kind in SHAPES:
        if reverses is not None:
            raise LedgerError("seule une contre-passation annule une transaction")
        debited, credited = SHAPES[kind]
    else:
        raise LedgerError(f"type de transaction inconnu : {kind}")
    for line in lines:
        expected = debited if line.side == Side.DEBIT else credited
        if line.account.kind != expected:
            raise LedgerError(f"{kind} : {line.side} sur {line.account.kind}, {expected} attendu")


def _signature(*, kind, provider_id, booking_id, reverses_id, lines) -> tuple:
    return (
        kind,
        provider_id,
        booking_id,
        reverses_id,
        tuple(sorted(lines)),
    )


def _existing(key: str, signature: tuple) -> LedgerTransaction | None:
    existing = LedgerTransaction.objects.filter(idempotency_key=key).first()
    if existing is None:
        return None
    stored = _signature(
        kind=existing.kind,
        provider_id=existing.provider_id,
        booking_id=existing.booking_id,
        reverses_id=existing.reverses_id,
        lines=[(e.account_id, e.side, e.amount_xof) for e in existing.entries.all()],
    )
    if stored != signature:
        raise LedgerError("clé d'idempotence déjà utilisée pour un autre mouvement")
    return existing


@transaction.atomic
def post_transaction(
    *,
    kind: str,
    lines: Sequence[Line],
    idempotency_key: str,
    actor_kind: str,
    actor=None,
    provider=None,
    booking=None,
    reverses: LedgerTransaction | None = None,
    reason_code: str = "",
    note: str = "",
) -> LedgerTransaction:
    """Écrit une transaction équilibrée, ou rend celle de même clé et de même contenu."""
    if not idempotency_key or len(idempotency_key) > 80:
        raise LedgerError("clé d'idempotence invalide")
    if actor_kind not in ActorKind.values or (actor is None) != (actor_kind == ActorKind.SYSTEM):
        raise LedgerError("acteur invalide")
    if len(note) > 200 or contains_pii(note):
        raise LedgerError("note invalide")
    _check_lines(kind=kind, lines=lines, provider=provider, reverses=reverses)

    signature = _signature(
        kind=kind,
        provider_id=provider.pk if provider else None,
        booking_id=booking.pk if booking else None,
        reverses_id=reverses.pk if reverses else None,
        lines=[(line.account.pk, line.side, line.amount_xof) for line in lines],
    )
    _lock_provider_accounts([line.account for line in lines])
    if (existing := _existing(idempotency_key, signature)) is not None:
        return existing
    try:
        with transaction.atomic():
            txn = LedgerTransaction.objects.create(
                kind=kind,
                idempotency_key=idempotency_key,
                provider=provider,
                booking=booking,
                reverses=reverses,
                reason_code=reason_code,
                note=note,
                actor=actor,
                actor_kind=actor_kind,
            )
            LedgerEntry.objects.bulk_create(
                LedgerEntry(
                    transaction=txn,
                    account=line.account,
                    side=line.side,
                    amount_xof=line.amount_xof,
                )
                for line in lines
            )
    except IntegrityError:
        # Même clé écrite entre-temps par une autre transaction (sans compte de pro à verrouiller).
        if (existing := _existing(idempotency_key, signature)) is not None:
            return existing
        raise
    # Vérifie l'équilibre maintenant, pas seulement au commit : le bug éclate chez l'appelant.
    with connection.cursor() as cursor:
        cursor.execute(f"SET CONSTRAINTS {BALANCE_TRIGGERS} IMMEDIATE")
        cursor.execute(f"SET CONSTRAINTS {BALANCE_TRIGGERS} DEFERRED")
    return txn


# --- Contre-passation --------------------------------------------------------------------------


def reversed_total(original: LedgerTransaction) -> int:
    """Montant déjà contre-passé d'une transaction (somme des débits de ses contre-passations)."""
    total = LedgerEntry.objects.filter(transaction__reverses=original, side=Side.DEBIT).aggregate(
        total=Sum("amount_xof")
    )["total"]
    return total or 0


def transaction_total(txn: LedgerTransaction) -> int:
    total = LedgerEntry.objects.filter(transaction=txn, side=Side.DEBIT).aggregate(
        total=Sum("amount_xof")
    )["total"]
    return total or 0


@transaction.atomic
def reverse(
    *,
    original: LedgerTransaction,
    amount_xof: int,
    idempotency_key: str,
    reason_code: str,
    note: str,
    actor,
    actor_kind: str = ActorKind.OPS,
) -> LedgerTransaction:
    """Contre-passe tout ou partie d'une transaction : lignes inversées. La somme des
    contre-passations d'une transaction ne dépasse jamais son montant (vérifié sous verrou)."""
    _check_amount(amount_xof)
    entries = list(original.entries.select_related("account"))
    _lock_provider_accounts([e.account for e in entries])
    total = transaction_total(original)
    if amount_xof < total and len(entries) != 2:
        raise LedgerError("contre-passation partielle d'une transaction à plus de deux lignes")
    # Un rejeu (même clé) est rendu tel quel par post_transaction : le plafond l'inclut déjà.
    if not LedgerTransaction.objects.filter(idempotency_key=idempotency_key).exists() and (
        reversed_total(original) + amount_xof > total
    ):
        raise LedgerError("contre-passation supérieure au montant restant")
    inverted = {Side.DEBIT: Side.CREDIT, Side.CREDIT: Side.DEBIT}
    lines = [
        Line(
            account=e.account,
            side=inverted[e.side],
            amount_xof=e.amount_xof if amount_xof == total else amount_xof,
        )
        for e in entries
    ]
    return post_transaction(
        kind=TransactionKind.REVERSAL,
        lines=lines,
        idempotency_key=idempotency_key,
        actor=actor,
        actor_kind=actor_kind,
        provider=original.provider,
        booking=original.booking,
        reverses=original,
        reason_code=reason_code,
        note=note,
    )
