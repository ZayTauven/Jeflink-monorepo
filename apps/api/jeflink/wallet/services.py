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
from datetime import datetime

from django.db import IntegrityError, connection, transaction
from django.db.models import Sum
from django.utils import timezone

from jeflink.common.alerts import alert_once
from jeflink.common.errors import DomainError
from jeflink.common.pii import contains_pii
from jeflink.notifications import events
from jeflink.trust.models import AuditEvent
from jeflink.trust.services import audit

from .commission import commission_xof
from .models import (
    PROVIDER_ACCOUNT_KINDS,
    RATE_BPS_MAX,
    V1_ACCOUNT_KINDS,
    AccountKind,
    ActorKind,
    Commission,
    CommissionRate,
    LedgerAccount,
    LedgerEntry,
    LedgerTransaction,
    Side,
    TransactionKind,
)
from .selectors import WalletState, provider_wallet, rate_for

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


def platform_account(kind: str, channel=None) -> LedgerAccount:
    """Compte de la plateforme (créé par migration ; recréé à la demande après un flush). Les
    fonds reçus (``platform_collections``) ont un compte par canal de règlement."""
    if kind in PROVIDER_ACCOUNT_KINDS:
        raise LedgerError(f"compte de pro demandé pour la plateforme : {kind}")
    if (kind == AccountKind.PLATFORM_COLLECTIONS) != (channel is not None):
        raise LedgerError("seuls les fonds reçus ont un compte par canal")
    account, _ = LedgerAccount.objects.get_or_create(kind=kind, provider=None, channel=channel)
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


def _signature(*, kind, provider_id, booking_id, intent_id, reverses_id, lines) -> tuple:
    return (kind, provider_id, booking_id, intent_id, reverses_id, tuple(sorted(lines)))


def _existing(key: str, signature: tuple) -> LedgerTransaction | None:
    existing = LedgerTransaction.objects.filter(idempotency_key=key).first()
    if existing is None:
        return None
    stored = _signature(
        kind=existing.kind,
        provider_id=existing.provider_id,
        booking_id=existing.booking_id,
        intent_id=existing.payment_intent_id,
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
    payment_intent=None,
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
        intent_id=payment_intent.pk if payment_intent else None,
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
                payment_intent=payment_intent,
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
        payment_intent=original.payment_intent,
        reverses=original,
        reason_code=reason_code,
        note=note,
    )


# --- Taux de commission ------------------------------------------------------------------------


def check_rate(
    *, trade, rate_bps: int, cap_xof: int | None, valid_from: datetime | None, note: str
) -> None:
    """Règles d'un nouveau taux, partagées par le service et le formulaire de l'admin.
    ``valid_from`` nul : en vigueur tout de suite."""
    if type(rate_bps) is not int or not 0 <= rate_bps <= RATE_BPS_MAX:
        raise DomainError("rate_invalid")
    if cap_xof is not None and (type(cap_xof) is not int or cap_xof <= 0):
        raise DomainError("rate_cap_invalid")
    if valid_from is not None and valid_from < timezone.now():
        raise DomainError("rate_valid_from_past")
    if len(note) > 200 or contains_pii(note):
        raise DomainError("note_invalid")
    if (
        valid_from is not None
        and CommissionRate.objects.filter(trade=trade, valid_from=valid_from).exists()
    ):
        raise DomainError("rate_duplicate", status=409)


@transaction.atomic
def add_rate(
    *,
    trade,
    rate_bps: int,
    cap_xof: int | None,
    valid_from: datetime | None,
    note: str,
    operator,
) -> CommissionRate:
    """Ajoute un taux (jamais de modification ni de suppression). Sans date : en vigueur tout de
    suite. Un taux déjà en vigueur ne change jamais une mission déjà devisée (ADR 0012)."""
    check_rate(trade=trade, rate_bps=rate_bps, cap_xof=cap_xof, valid_from=valid_from, note=note)
    immediate = valid_from is None
    rate = CommissionRate.objects.create(
        trade=trade,
        rate_bps=rate_bps,
        cap_xof=cap_xof,
        valid_from=timezone.now() if immediate else valid_from,
        note=note,
        created_by=operator,
    )
    audit(
        action="wallet.rate.added",
        actor=operator,
        target=rate,
        metadata={
            "trade": trade.slug if trade is not None else "",
            "rate_bps": rate_bps,
            "cap_xof": cap_xof,
            "immediate": immediate,
        },
    )
    return rate


@transaction.atomic
def seed_rates() -> int:
    """Taux de lancement par métier (spec 005, Q1), chargés par ``seed_reference_data`` comme
    les métiers : seulement pour un métier qui existe et n'a encore aucun taux. Renvoie le nombre
    de taux créés."""
    from jeflink.catalog.selectors import trade_by_slug

    from .reference_data import LAUNCH_TRADE_RATES

    created = 0
    for data in LAUNCH_TRADE_RATES:
        trade = trade_by_slug(data["trade"])
        if trade is None or CommissionRate.objects.filter(trade=trade).exists():
            continue
        CommissionRate.objects.create(
            trade=trade,
            rate_bps=data["rate_bps"],
            cap_xof=data["cap_xof"],
            valid_from=timezone.now(),
            note="Taux de lancement (spec 005)",
        )
        created += 1
    return created


# --- Seuils de dette ---------------------------------------------------------------------------


def notify_state_change(provider, before: WalletState, after: WalletState) -> None:
    """Prévient le pro quand sa dette franchit un seuil, une fois par franchissement (après
    commit). Référence : ``public_id`` de la fiche pro."""
    if before == after:
        return
    if after == WalletState.BLOCKED:
        kind = events.WALLET_QUOTES_BLOCKED
    elif before == WalletState.BLOCKED:
        kind = events.WALLET_QUOTES_UNBLOCKED
    elif after == WalletState.ALERT:
        kind = events.WALLET_DEBT_ALERT
    else:
        return  # d'alerte à ok : rien à annoncer
    events.notify(kind, [provider.owner], provider.public_id)


# --- Commission à la clôture -------------------------------------------------------------------


def _exempt(booking, reason: str, **copies) -> Commission:
    return Commission.objects.create(
        booking=booking,
        status=Commission.Status.EXEMPT,
        exempt_reason=reason,
        amount_xof=0,
        **copies,
    )


def charge_commission_on_close(booking, reason: str) -> None:
    """Gestionnaire de clôture (``register_close_handler``) : écrit la commission de la
    réservation, dans la transaction de la clôture, réservation et fiche pro verrouillées.

    Idempotent (une commission par réservation). Ne lève jamais d'erreur métier : la clôture ne
    reste pas bloquée par le portefeuille ; une erreur de programmation l'annule, ``close_due``
    la retente. Assiette : ``amount_xof`` à la clôture (avenants acceptés compris) ; taux en
    vigueur à l'envoi du devis (ADR 0012)."""
    if Commission.objects.filter(booking=booking).exists():
        return
    provider = booking.provider
    trade = booking.request.trade
    copies = {
        "provider": provider,
        "trade": trade,
        "base_xof": booking.amount_xof,
        "completion_method": booking.completion_method,
        "close_reason": reason[:24],
    }
    rate = rate_for(trade=trade, at=booking.quote.created_at)
    if rate is not None:
        copies |= {"rate": rate, "rate_bps": rate.rate_bps, "cap_xof": rate.cap_xof}

    if booking.client.is_review_account:
        commission = _exempt(booking, Commission.ExemptReason.REVIEW_ACCOUNT, **copies)
    elif rate is None:
        commission = _exempt(booking, Commission.ExemptReason.RATE_MISSING, **copies)
        alert_once(
            f"wallet_rate_missing:{booking.public_id}",
            86_400,
            "wallet_rate_missing",
            booking=booking.public_id,
        )
    elif rate.rate_bps == 0:
        commission = _exempt(booking, Commission.ExemptReason.ZERO_RATE, **copies)
    elif (amount := commission_xof(booking.amount_xof, rate.rate_bps, rate.cap_xof)) == 0:
        commission = _exempt(booking, Commission.ExemptReason.ZERO_AMOUNT, **copies)
    else:
        before = provider_wallet(provider).state
        txn = post_transaction(
            kind=TransactionKind.COMMISSION,
            lines=[
                Line(provider_account(provider), Side.DEBIT, amount),
                Line(platform_account(AccountKind.PLATFORM_REVENUE), Side.CREDIT, amount),
            ],
            idempotency_key=f"commission:{booking.public_id}",
            actor_kind=ActorKind.SYSTEM,
            provider=provider,
            booking=booking,
        )
        commission = Commission.objects.create(
            booking=booking,
            status=Commission.Status.CHARGED,
            amount_xof=amount,
            ledger_transaction=txn,
            **copies,
        )
        notify_state_change(provider, before, provider_wallet(provider).state)
    audit(
        action="wallet.commission.recorded",
        actor_kind=AuditEvent.ActorKind.SYSTEM,
        target=commission,
        metadata={
            "status": commission.status,
            "exempt_reason": commission.exempt_reason,
            "amount_xof": commission.amount_xof,
            "rate_bps": commission.rate_bps,
            "completion_method": commission.completion_method,
            "close_reason": commission.close_reason,
        },
    )


# --- Règlements --------------------------------------------------------------------------------


def record_settlement(*, intent, operator) -> LedgerTransaction:
    """Écrit un règlement confirmé (appelé par ``payments.services``, jamais l'inverse) : fonds
    reçus sur le compte du canal, dette du pro diminuée du montant réellement reçu. Un excédent
    devient un avoir. Idempotent par intention."""
    amount = _check_amount(intent.received_xof)
    provider = intent.provider
    return post_transaction(
        kind=TransactionKind.SETTLEMENT,
        lines=[
            Line(
                platform_account(AccountKind.PLATFORM_COLLECTIONS, intent.channel),
                Side.DEBIT,
                amount,
            ),
            Line(provider_account(provider), Side.CREDIT, amount),
        ],
        idempotency_key=f"settlement:{intent.public_id}",
        actor=operator,
        actor_kind=ActorKind.OPS,
        provider=provider,
        payment_intent=intent,
    )


# --- Ajustements de la Comptabilité ------------------------------------------------------------

ADJUSTMENT_REASONS = (
    "dispute_refund",
    "no_payment",
    "entry_error",
    "goodwill",
    "duplicate_settlement",
    "other",
)


def _lock_provider(provider):
    from jeflink.providers.models import Provider

    return Provider.objects.select_for_update().select_related("owner").get(pk=provider.pk)


def _check_adjustment(*, provider, operator, reason_code: str, note: str, key: str) -> str:
    if provider.owner_id == operator.pk:
        raise DomainError("operator_is_provider", status=403)
    if reason_code not in ADJUSTMENT_REASONS:
        raise DomainError("adjustment_reason_invalid", status=422)
    note = " ".join((note or "").split())
    if not 1 <= len(note) <= 200 or contains_pii(note):
        raise DomainError("note_invalid", status=422)
    if not key or len(key) > 64:
        raise DomainError("idempotency_key_required")
    return note


def _check_adjustment_amount(amount_xof: object) -> int:
    if type(amount_xof) is not int or amount_xof <= 0:
        raise DomainError("adjustment_amount_invalid", status=422)
    return amount_xof


def _adjust(*, provider, operator, kind: str, key: str, write) -> LedgerTransaction:
    """Écrit un ajustement (``write()`` rend la transaction), une seule fois par clé : audité,
    notifié au pro, seuils réévalués."""
    if (existing := LedgerTransaction.objects.filter(idempotency_key=key).first()) is not None:
        return existing  # rejeu du même formulaire
    before = provider_wallet(provider).state
    txn = write()
    audit(
        action="wallet.adjustment.posted",
        actor=operator,
        actor_kind=AuditEvent.ActorKind.OPS,
        target=txn,
        metadata={
            "type": kind,
            "amount_xof": transaction_total(txn),
            "reason_code": txn.reason_code,
        },
    )
    events.notify(events.WALLET_ADJUSTMENT_POSTED, [provider.owner], txn.public_id)
    notify_state_change(provider, before, provider_wallet(provider).state)
    return txn


@transaction.atomic
def waive_commission(
    *, commission: Commission, amount_xof: int, reason_code: str, note: str, operator, key: str
) -> LedgerTransaction:
    """Avoir sur une commission (pro qui a remboursé le client, client parti sans payer...) :
    contre-passation partielle ou totale, jamais au-delà de ce qui reste."""
    provider = _lock_provider(commission.provider)
    note = _check_adjustment(
        provider=provider, operator=operator, reason_code=reason_code, note=note, key=key
    )
    amount_xof = _check_adjustment_amount(amount_xof)
    original = commission.ledger_transaction
    if original is None:
        raise DomainError("adjustment_not_allowed", status=409)
    key = f"reversal:{key}"

    def write():
        _lock_provider_accounts([provider_account(provider)])
        if reversed_total(original) + amount_xof > transaction_total(original):
            raise DomainError("adjustment_exceeds_remaining", status=422)
        return reverse(
            original=original,
            amount_xof=amount_xof,
            idempotency_key=key,
            reason_code=reason_code,
            note=note,
            actor=operator,
        )

    return _adjust(provider=provider, operator=operator, kind="waiver", key=key, write=write)


@transaction.atomic
def reverse_settlement(*, intent, reason_code: str, note: str, operator, key: str):
    """Contre-passation d'un règlement confirmé à tort (doublon, versement introuvable après
    coup) : la dette du pro revient, pour tout ce qui n'a pas déjà été contre-passé."""
    provider = _lock_provider(intent.provider)
    note = _check_adjustment(
        provider=provider, operator=operator, reason_code=reason_code, note=note, key=key
    )
    original = LedgerTransaction.objects.filter(
        kind=TransactionKind.SETTLEMENT, payment_intent_id=intent.pk
    ).first()
    if original is None:
        raise DomainError("adjustment_not_allowed", status=409)
    key = f"reversal:{key}"

    def write():
        _lock_provider_accounts([provider_account(provider)])
        remaining = transaction_total(original) - reversed_total(original)
        if remaining <= 0:
            raise DomainError("adjustment_exceeds_remaining", status=422)
        return reverse(
            original=original,
            amount_xof=remaining,
            idempotency_key=key,
            reason_code=reason_code,
            note=note,
            actor=operator,
        )

    return _adjust(
        provider=provider, operator=operator, kind="settlement_reversal", key=key, write=write
    )


@transaction.atomic
def post_goodwill_credit(
    *, provider, amount_xof: int, reason_code: str, note: str, operator, key: str
) -> LedgerTransaction:
    """Geste commercial : la dette du pro baisse (ou un avoir naît), à la charge de Jeflink."""
    return _post_adjustment(
        provider=provider,
        kind=TransactionKind.GOODWILL_CREDIT,
        accounts=lambda p: (platform_account(AccountKind.PLATFORM_GOODWILL), provider_account(p)),
        amount_xof=amount_xof,
        reason_code=reason_code,
        note=note,
        operator=operator,
        key=key,
    )


@transaction.atomic
def post_correction_debit(
    *, provider, amount_xof: int, reason_code: str, note: str, operator, key: str, booking=None
) -> LedgerTransaction:
    """Correction en faveur de Jeflink (commission oubliée, taux manquant) : la dette augmente.
    Rattachée à la réservation quand il y en a une."""
    if booking is not None and booking.provider_id != provider.pk:
        raise DomainError("adjustment_not_allowed", status=409)
    return _post_adjustment(
        provider=provider,
        kind=TransactionKind.CORRECTION_DEBIT,
        accounts=lambda p: (provider_account(p), platform_account(AccountKind.PLATFORM_REVENUE)),
        amount_xof=amount_xof,
        reason_code=reason_code,
        note=note,
        operator=operator,
        key=key,
        booking=booking,
    )


def _post_adjustment(
    *, provider, kind, accounts, amount_xof, reason_code, note, operator, key, booking=None
) -> LedgerTransaction:
    """``accounts(provider)`` rend (compte débité, compte crédité)."""
    provider = _lock_provider(provider)
    note = _check_adjustment(
        provider=provider, operator=operator, reason_code=reason_code, note=note, key=key
    )
    amount_xof = _check_adjustment_amount(amount_xof)
    prefix = "goodwill" if kind == TransactionKind.GOODWILL_CREDIT else "correction"
    ledger_key = f"{prefix}:{key}"

    def write():
        debited, credited = accounts(provider)
        return post_transaction(
            kind=kind,
            lines=[
                Line(debited, Side.DEBIT, amount_xof),
                Line(credited, Side.CREDIT, amount_xof),
            ],
            idempotency_key=ledger_key,
            actor=operator,
            actor_kind=ActorKind.OPS,
            provider=provider,
            booking=booking,
            reason_code=reason_code,
            note=note,
        )

    return _adjust(provider=provider, operator=operator, kind=kind, key=ledger_key, write=write)
