"""Écritures du domaine ``payments`` (spec 005) : canaux et règlements de commission.

``payments`` appelle ``wallet``, jamais l'inverse (ADR 0012). Toute création ou décision passe
par la passerelle du canal (règle 3), puis un règlement confirmé s'écrit au grand livre
(``wallet.services.record_settlement``).

Ordre des verrous : compte du gérant, fiche pro, intention de paiement, comptes du grand livre du
pro (pris par ``wallet``). La référence de transaction et les 4 derniers chiffres du payeur ne
vont jamais dans un audit, un log ni un message d'erreur.
"""

import hashlib
import hmac
import json
import re
from dataclasses import dataclass
from datetime import datetime

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Q, Sum
from django.utils import timezone

from jeflink.accounts.models import User
from jeflink.common.alerts import alert_once
from jeflink.common.errors import DomainError
from jeflink.common.pii import contains_pii
from jeflink.common.ratelimit import Limit, RateLimitUnavailable, consume
from jeflink.notifications import events
from jeflink.providers.models import Provider
from jeflink.requests.services import IDEMPOTENCY_KEY
from jeflink.trust.models import AuditEvent
from jeflink.trust.services import audit
from jeflink.wallet import services as wallet
from jeflink.wallet.selectors import provider_wallet, settlement_reversals

from .gateways import FAKE_ALLOWED_ENVS, get_gateway
from .models import Gateway, PaymentIntent, SettlementChannel

Status = PaymentIntent.Status
REFERENCE = re.compile(r"^[A-Z0-9._-]{6,40}$")
PAYER_LAST4 = re.compile(r"^[0-9]{4}$")
DECLARE_LIMIT = Limit("payments:declare", 10, 24 * 3600)
# Passerelles qu'un pro peut déclarer lui-même (les espèces sont saisies par l'Ops).
DECLARABLE = frozenset({Gateway.MANUAL_MOBILE_MONEY, Gateway.FAKE})
# Rejets qui retirent la confiance : les déclarations suivantes ne comptent plus comme payées
# avant qu'un règlement soit confirmé en entier (revue terrain B1, revue sécurité 2).
DISTRUST_REJECTIONS = (
    PaymentIntent.RejectReason.NOT_FOUND,
    PaymentIntent.RejectReason.DUPLICATE,
    PaymentIntent.RejectReason.AMOUNT_MISMATCH,
)


@dataclass(frozen=True)
class CreatedIntent:
    intent: PaymentIntent
    created: bool  # False : même clé et même contenu, l'intention existante est rendue


# --- Canaux ------------------------------------------------------------------------------------


@transaction.atomic
def save_channel(*, channel: SettlementChannel, operator) -> SettlementChannel:
    """Crée ou modifie un canal de règlement : slug figé, contraintes vérifiées, audité. Un canal
    ne se supprime pas : on le désactive."""
    created = channel.pk is None
    if channel.gateway == Gateway.FAKE and settings.DJANGO_ENV not in FAKE_ALLOWED_ENVS:
        raise ValidationError("Passerelle factice interdite hors local et test.")
    changed: list[str] = []
    if not created:
        stored = SettlementChannel.objects.get(pk=channel.pk)
        if (stored.slug, stored.gateway) != (channel.slug, channel.gateway):
            raise ValidationError("Le slug et la passerelle d'un canal sont figés.")
        changed = [
            name
            for name in CHANNEL_EDITABLE_FIELDS
            if getattr(stored, name) != getattr(channel, name)
        ]
    channel.full_clean()
    channel.save()
    audit(
        action="payments.channel.saved",
        actor=operator,
        target=channel,
        metadata={
            "slug": channel.slug,
            "gateway": channel.gateway,
            "is_active": channel.is_active,
            "created": created,
            "changed_fields": changed,  # noms des champs seulement
        },
    )
    if "account_display" in changed:
        # Le numéro où les pros paient a changé : l'Ops le sait tout de suite.
        alert_once(
            f"wallet_channel_account_changed:{channel.public_id}",
            300,
            "wallet_channel_account_changed",
            channel=channel.slug,
        )
    return channel


CHANNEL_EDITABLE_FIELDS = (
    "label_fr",
    "label_wo",
    "account_display",
    "instructions_fr",
    "instructions_wo",
    "is_active",
    "position",
)


# --- Règles de saisie --------------------------------------------------------------------------


def normalize_reference(raw: str) -> str:
    """Référence de la transaction : espaces retirés, majuscules, 6 à 40 caractères
    ``[A-Z0-9._-]``, et jamais un numéro de téléphone."""
    reference = "".join((raw or "").split()).upper()
    if not REFERENCE.match(reference) or contains_pii(reference):
        raise DomainError("settlement_reference_invalid", status=422)
    return reference


def _clean_payer_last4(raw: str) -> str:
    value = (raw or "").strip()
    if value and not PAYER_LAST4.match(value):
        raise DomainError("payer_last4_invalid", status=422)
    return value


def _clean_paid_at(paid_at: datetime, now: datetime) -> datetime:
    if paid_at > now + settings.WALLET_SETTLEMENT_CLOCK_SKEW or (
        paid_at < now - settings.WALLET_SETTLEMENT_MAX_AGE
    ):
        raise DomainError("paid_at_invalid", status=422)
    return paid_at


def _clean_amount(amount_xof: object) -> int:
    if type(amount_xof) is not int or amount_xof <= 0:
        raise DomainError("settlement_amount_invalid", status=422)
    return amount_xof


def _clean_note(note: str) -> str:
    note = " ".join((note or "").split())
    if len(note) > 200 or contains_pii(note):
        raise DomainError("note_invalid", status=422)
    return note


def _payload_hash(*parts: object) -> str:
    body = json.dumps([str(part) for part in parts], ensure_ascii=False)
    return hmac.new(settings.PII_HMAC_KEY.encode(), body.encode(), hashlib.sha256).hexdigest()


# --- Ce qui compte comme payé ------------------------------------------------------------------


def distrusted_since(provider) -> datetime | None:
    """Depuis quand les déclarations du pro ne comptent plus comme payées (``None`` : elles
    comptent). La confiance se perd par un rejet « introuvable », « doublon » ou « montant
    différent », par une confirmation d'un montant reçu inférieur au déclaré, ou par la
    contre-passation d'un règlement ; elle ne revient qu'avec une confirmation où le montant
    reçu couvre le déclaré, jamais contre-passée depuis."""
    reversed_at = settlement_reversals(provider)
    distrust = list(reversed_at.values())
    trust = []
    decided = PaymentIntent.objects.filter(provider=provider, decided_at__isnull=False)
    for pk, status, reason, declared, received, decided_at in decided.values_list(
        "pk", "status", "reject_reason", "declared_xof", "received_xof", "decided_at"
    ):
        if (status == Status.REJECTED and reason in DISTRUST_REJECTIONS) or (
            status == Status.CONFIRMED and received < declared
        ):
            distrust.append(decided_at)
        elif status == Status.CONFIRMED and pk not in reversed_at:
            trust.append(decided_at)
    if not distrust:
        return None
    last_distrust = max(distrust)
    if trust and max(trust) > last_distrust:
        return None
    return last_distrust


def counted_pending_xof(provider) -> int:
    """Montant des déclarations qui comptent comme payées (source inscrite auprès de
    ``wallet.selectors``) : toute déclaration en attente de décision, sans limite de durée,
    sauf celles faites depuis que la confiance est perdue (``distrusted_since``)."""
    pending = PaymentIntent.objects.filter(
        provider=provider, status__in=PaymentIntent.PENDING_STATUSES
    )
    if (since := distrusted_since(provider)) is not None:
        pending = pending.filter(created_at__lt=since)
    return pending.aggregate(total=Sum("declared_xof"))["total"] or 0


def _pending_total(provider, *, excluding: PaymentIntent | None = None) -> int:
    pending = PaymentIntent.objects.filter(
        provider=provider, status__in=PaymentIntent.PENDING_STATUSES
    )
    if excluding is not None:
        pending = pending.exclude(pk=excluding.pk)
    return pending.aggregate(total=Sum("declared_xof"))["total"] or 0


# --- Verrous -----------------------------------------------------------------------------------


def _lock_owner_and_provider(provider: Provider) -> Provider:
    """Compte du gérant puis fiche : une déclaration naît sous le verrou du compte (bloqueur
    de suppression)."""
    owner = User.objects.select_for_update(no_key=True).get(pk=provider.owner_id)
    if not owner.is_active or owner.is_deleted:
        raise DomainError("account_inactive", status=403)
    return Provider.objects.select_for_update().get(pk=provider.pk)


def _lock_intent(intent: PaymentIntent) -> tuple[Provider, PaymentIntent]:
    provider = Provider.objects.select_for_update().get(pk=intent.provider_id)
    locked = PaymentIntent.objects.select_for_update().select_related("channel").get(pk=intent.pk)
    return provider, locked


def _refuse_own_account(provider: Provider, operator) -> None:
    if provider.owner_id == operator.pk:
        raise DomainError("operator_is_provider", status=403)


def _refuse_other_provider(intent: PaymentIntent, actor) -> None:
    if intent.provider.owner_id != actor.pk:
        raise DomainError("not_found", status=404)


def _replay(provider: Provider, key: str, digest: str) -> PaymentIntent | None:
    existing = PaymentIntent.objects.filter(provider=provider, idempotency_key=key).first()
    if existing is None:
        return None
    if existing.payload_hash != digest:
        raise DomainError("idempotency_key_reused", status=409)
    return existing


def _audit(action: str, intent: PaymentIntent, actor, actor_kind: str, **metadata) -> None:
    audit(action=action, actor=actor, actor_kind=actor_kind, target=intent, metadata=metadata)


# --- Le pro déclare ----------------------------------------------------------------------------


def declare_settlement(
    *,
    provider: Provider,
    actor,
    channel: SettlementChannel,
    amount_xof: int,
    reference: str,
    paid_at: datetime,
    payer_last4: str,
    idempotency_key: str,
) -> CreatedIntent:
    """Le gérant déclare avoir payé (mobile money vers le numéro marchand). Un pro suspendu le
    peut. Idempotent par ``(pro, Idempotency-Key)`` ; même clé, autre contenu : 409."""
    if actor.pk != provider.owner_id:
        raise DomainError("not_found", status=404)
    if not IDEMPOTENCY_KEY.match(idempotency_key or ""):
        raise DomainError("idempotency_key_required")
    amount_xof = _clean_amount(amount_xof)
    reference = normalize_reference(reference)
    payer_last4 = _clean_payer_last4(payer_last4)
    paid_at = _clean_paid_at(paid_at, timezone.now())
    digest = _payload_hash(channel.pk, amount_xof, reference, paid_at.isoformat(), payer_last4)
    if (existing := _replay(provider, idempotency_key, digest)) is not None:
        return CreatedIntent(existing, created=False)
    try:
        outcome = consume([(DECLARE_LIMIT, str(actor.public_id))])
    except RateLimitUnavailable:
        raise DomainError("settlement_rate_limited", status=429) from None
    if not outcome.allowed:
        raise DomainError("settlement_rate_limited", status=429, retry_after=outcome.retry_after)
    try:
        with transaction.atomic():
            intent = _insert_declaration(
                provider=provider,
                actor=actor,
                channel=channel,
                amount_xof=amount_xof,
                reference=reference,
                paid_at=paid_at,
                payer_last4=payer_last4,
                key=idempotency_key,
                digest=digest,
            )
    except IntegrityError:
        if (existing := _replay(provider, idempotency_key, digest)) is not None:
            return CreatedIntent(existing, created=False)
        raise DomainError("settlement_reference_used", status=409) from None
    return CreatedIntent(intent, created=True)


def _insert_declaration(
    *, provider, actor, channel, amount_xof, reference, paid_at, payer_last4, key, digest
) -> PaymentIntent:
    provider = _lock_owner_and_provider(provider)
    channel = SettlementChannel.objects.get(pk=channel.pk)
    if not channel.is_active or channel.gateway not in DECLARABLE:
        raise DomainError("channel_inactive", status=422)
    open_count = PaymentIntent.objects.filter(
        provider=provider, status__in=PaymentIntent.PENDING_STATUSES
    ).count()
    if open_count >= settings.WALLET_SETTLEMENT_MAX_PENDING:
        raise DomainError("settlement_pending_limit", status=409)
    payable = provider_wallet(provider).due_xof - _pending_total(provider)
    if payable <= 0:
        raise DomainError("nothing_due", status=409)
    if amount_xof > payable:
        raise DomainError("settlement_exceeds_due", status=422, payable_xof=payable)
    if _reference_used(channel, reference, provider=provider):
        raise DomainError("settlement_reference_used", status=409)
    before = provider_wallet(provider).state
    intent = PaymentIntent(
        purpose=PaymentIntent.Purpose.COMMISSION_SETTLEMENT,
        gateway=channel.gateway,
        channel=channel,
        provider=provider,
        origin=PaymentIntent.Origin.PRO_DECLARED,
        declared_xof=amount_xof,
        reference=reference,
        paid_at=paid_at,
        payer_last4=payer_last4,
        idempotency_key=key,
        payload_hash=digest,
        declared_by=actor,
    )
    intent.status = get_gateway(channel.gateway).create_intent(intent=intent).status
    intent.save()
    _audit(
        "payments.settlement.declared",
        intent,
        actor,
        AuditEvent.ActorKind.USER,
        amount_xof=amount_xof,
        channel=channel.slug,
    )
    wallet.notify_state_change(provider, before, provider_wallet(provider).state)
    return intent


def _reference_used(
    channel: SettlementChannel, reference: str, *, provider=None, excluding=None
) -> bool:
    """Une transaction ne règle jamais deux fois sur un canal (intentions vivantes de tous les
    pros) ; un pro ne réutilise jamais une référence qu'il a déjà déclarée, même retirée ou
    rejetée (revue sécurité 1)."""
    same = PaymentIntent.objects.filter(channel=channel, reference=reference)
    if excluding is not None:
        same = same.exclude(pk=excluding.pk)
    used = same.exclude(status__in=PaymentIntent.CLOSED_WITHOUT_PAYMENT)
    if provider is not None:
        used = used | same.filter(provider=provider)
    return used.exists()


def can_cancel(intent: PaymentIntent, *, now: datetime | None = None) -> bool:
    if intent.status not in PaymentIntent.PENDING_STATUSES:
        return False
    since = intent.corrected_at or intent.created_at
    return (now or timezone.now()) - since <= settings.WALLET_SETTLEMENT_CANCEL_WINDOW


@transaction.atomic
def cancel_settlement(*, intent: PaymentIntent, actor) -> PaymentIntent:
    """Le pro retire une déclaration encore en attente de décision, seulement dans les
    ``WALLET_SETTLEMENT_CANCEL_WINDOW`` qui suivent sa déclaration ou sa correction (faute de
    frappe). Au-delà, seule l'Ops décide : retirer pour redéclarer ne prolonge pas l'effet d'une
    déclaration (revue sécurité 1)."""
    _refuse_other_provider(intent, actor)
    provider, intent = _lock_intent(intent)
    if intent.status not in PaymentIntent.PENDING_STATUSES:
        raise DomainError("settlement_not_pending", status=409)
    if not can_cancel(intent):
        raise DomainError("settlement_not_cancellable", status=409)
    before = provider_wallet(provider).state
    intent.status = Status.CANCELLED
    intent.save(update_fields=["status", "updated_at"])
    _audit(
        "payments.settlement.cancelled",
        intent,
        actor,
        AuditEvent.ActorKind.USER,
        amount_xof=intent.declared_xof,
    )
    wallet.notify_state_change(provider, before, provider_wallet(provider).state)
    return intent


@transaction.atomic
def correct_settlement(
    *,
    intent: PaymentIntent,
    actor,
    amount_xof: int,
    reference: str,
    paid_at: datetime,
    payer_last4: str,
) -> PaymentIntent:
    """Le pro corrige une déclaration que l'Ops lui a renvoyée, une seule fois. Mêmes règles que
    la déclaration ; elle redevient « à rapprocher »."""
    _refuse_other_provider(intent, actor)
    amount_xof = _clean_amount(amount_xof)
    reference = normalize_reference(reference)
    payer_last4 = _clean_payer_last4(payer_last4)
    paid_at = _clean_paid_at(paid_at, timezone.now())
    provider, intent = _lock_intent(intent)
    if intent.status != Status.NEEDS_CORRECTION:
        raise DomainError("settlement_not_correctable", status=409)
    if not intent.channel.is_active or intent.channel.gateway not in DECLARABLE:
        raise DomainError("channel_inactive", status=422)
    payable = provider_wallet(provider).due_xof - _pending_total(provider, excluding=intent)
    if amount_xof > payable:
        raise DomainError("settlement_exceeds_due", status=422, payable_xof=max(payable, 0))
    if _reference_used(intent.channel, reference, provider=provider, excluding=intent):
        raise DomainError("settlement_reference_used", status=409)
    before = provider_wallet(provider).state
    intent.declared_xof = amount_xof
    intent.reference = reference
    intent.paid_at = paid_at
    intent.payer_last4 = payer_last4
    intent.status = Status.DECLARED
    intent.corrected_at = timezone.now()
    try:
        with transaction.atomic():
            intent.save()
    except IntegrityError:
        raise DomainError("settlement_reference_used", status=409) from None
    _audit(
        "payments.settlement.corrected",
        intent,
        actor,
        AuditEvent.ActorKind.USER,
        amount_xof=amount_xof,
    )
    wallet.notify_state_change(provider, before, provider_wallet(provider).state)
    return intent


# --- L'Ops décide ------------------------------------------------------------------------------


@transaction.atomic
def confirm_settlement(*, intent: PaymentIntent, operator, received_xof: int) -> PaymentIntent:
    """L'Ops (groupe « Rapprochement ») a retrouvé le versement dans le relevé : confirmé avec le
    montant réellement reçu, puis écrit au grand livre. Jamais sur son propre compte pro."""
    received_xof = _clean_amount(received_xof)
    provider, intent = _lock_intent(intent)
    _refuse_own_account(provider, operator)
    if intent.status not in PaymentIntent.PENDING_STATUSES:
        raise DomainError("settlement_not_pending", status=409)
    before = provider_wallet(provider).state
    _confirm(intent, operator=operator, received_xof=received_xof)
    _audit(
        "payments.settlement.confirmed",
        intent,
        operator,
        AuditEvent.ActorKind.OPS,
        declared_xof=intent.declared_xof,
        received_xof=received_xof,
        difference_xof=received_xof - intent.declared_xof,
        channel=intent.channel.slug,
        origin=intent.origin,
    )
    events.notify(events.WALLET_SETTLEMENT_CONFIRMED, [provider.owner], intent.public_id)
    wallet.notify_state_change(provider, before, provider_wallet(provider).state)
    return intent


def _confirm(intent: PaymentIntent, *, operator, received_xof: int) -> None:
    result = get_gateway(intent.gateway).confirm(intent=intent, received_xof=received_xof)
    intent.status = result.status
    intent.received_xof = received_xof
    intent.decided_by = operator
    intent.decided_at = timezone.now()
    intent.save(update_fields=["status", "received_xof", "decided_by", "decided_at", "updated_at"])
    wallet.record_settlement(intent=intent, operator=operator)


@transaction.atomic
def request_correction(*, intent: PaymentIntent, operator, reason: str) -> PaymentIntent:
    """L'Ops ne retrouve pas le versement tel que déclaré : la déclaration revient au pro, une
    seule fois. Ce n'est pas un rejet : elle continue de compter comme payée."""
    if reason not in PaymentIntent.CorrectionReason.values:
        raise DomainError("correction_reason_invalid", status=422)
    provider, intent = _lock_intent(intent)
    _refuse_own_account(provider, operator)
    if intent.status != Status.DECLARED or intent.corrected_at is not None:
        raise DomainError("settlement_not_correctable", status=409)
    if intent.origin != PaymentIntent.Origin.PRO_DECLARED:
        raise DomainError("settlement_not_correctable", status=409)
    intent.status = Status.NEEDS_CORRECTION
    intent.correction_reason = reason
    intent.save(update_fields=["status", "correction_reason", "updated_at"])
    _audit(
        "payments.settlement.correction_requested",
        intent,
        operator,
        AuditEvent.ActorKind.OPS,
        reason=reason,
    )
    events.notify(events.WALLET_SETTLEMENT_NEEDS_CORRECTION, [provider.owner], intent.public_id)
    return intent


@transaction.atomic
def reject_settlement(*, intent: PaymentIntent, operator, reason: str, note: str) -> PaymentIntent:
    """L'Ops rejette une déclaration, avec un motif. Elle cesse de compter comme payée ; après un
    rejet « introuvable » ou « doublon », les déclarations suivantes du pro ne comptent plus
    avant une confirmation."""
    if reason not in PaymentIntent.RejectReason.values:
        raise DomainError("reject_reason_invalid", status=422)
    note = _clean_note(note)
    provider, intent = _lock_intent(intent)
    _refuse_own_account(provider, operator)
    if intent.status not in PaymentIntent.PENDING_STATUSES:
        raise DomainError("settlement_not_pending", status=409)
    before = provider_wallet(provider).state
    intent.status = Status.REJECTED
    intent.reject_reason = reason
    intent.decision_note = note
    intent.decided_by = operator
    intent.decided_at = timezone.now()
    intent.save(
        update_fields=[
            "status", "reject_reason", "decision_note", "decided_by", "decided_at", "updated_at",
        ]
    )  # fmt: skip
    _audit(
        "payments.settlement.rejected",
        intent,
        operator,
        AuditEvent.ActorKind.OPS,
        reason=reason,
        declared_xof=intent.declared_xof,
    )
    events.notify(events.WALLET_SETTLEMENT_REJECTED, [provider.owner], intent.public_id)
    wallet.notify_state_change(provider, before, provider_wallet(provider).state)
    return intent


# --- L'Ops saisit un règlement -----------------------------------------------------------------


def record_mobile_money_settlement(
    *,
    provider: Provider,
    operator,
    channel: SettlementChannel,
    amount_xof: int,
    reference: str,
    paid_at: datetime,
    idempotency_key: str,
) -> CreatedIntent:
    """Versement vu dans le relevé marchand, venu du numéro du pro : crédité sans déclaration.
    Même unicité de la référence : une déclaration du pro arrivée ensuite est refusée."""
    if channel.gateway not in DECLARABLE:
        raise DomainError("channel_inactive", status=422)
    reference = normalize_reference(reference)
    paid_at = _clean_paid_at(paid_at, timezone.now())
    return _record_by_ops(
        provider=provider,
        operator=operator,
        channel=channel,
        amount_xof=amount_xof,
        fields={"reference": reference, "paid_at": paid_at},
        idempotency_key=idempotency_key,
    )


def record_cash_settlement(
    *,
    provider: Provider,
    operator,
    channel: SettlementChannel,
    amount_xof: int,
    receipt_number: str,
    idempotency_key: str,
) -> CreatedIntent:
    """Espèces remises au bureau, avec un numéro de reçu : créées et confirmées en un geste."""
    if channel.gateway != Gateway.CASH:
        raise DomainError("channel_inactive", status=422)
    receipt = " ".join((receipt_number or "").split())
    if not 1 <= len(receipt) <= 40 or contains_pii(receipt):
        raise DomainError("receipt_number_invalid", status=422)
    return _record_by_ops(
        provider=provider,
        operator=operator,
        channel=channel,
        amount_xof=amount_xof,
        fields={"receipt_number": receipt, "paid_at": timezone.now()},
        idempotency_key=idempotency_key,
    )


def _record_by_ops(
    *, provider, operator, channel, amount_xof, fields, idempotency_key
) -> CreatedIntent:
    amount_xof = _clean_amount(amount_xof)
    if not idempotency_key or len(idempotency_key) > 80:
        raise DomainError("idempotency_key_required")
    _refuse_own_account(provider, operator)
    digest = _payload_hash(channel.pk, amount_xof, *sorted(map(str, fields.values())))
    if (existing := _replay(provider, idempotency_key, digest)) is not None:
        return CreatedIntent(existing, created=False)
    try:
        with transaction.atomic():
            provider = _lock_owner_and_provider(provider)
            if fields.get("reference") and _reference_used(channel, fields["reference"]):
                raise DomainError("settlement_reference_used", status=409)
            if fields.get("receipt_number") and _receipt_used(channel, fields["receipt_number"]):
                raise DomainError("receipt_number_used", status=409)
            before = provider_wallet(provider).state
            intent = PaymentIntent(
                purpose=PaymentIntent.Purpose.COMMISSION_SETTLEMENT,
                gateway=channel.gateway,
                channel=channel,
                provider=provider,
                origin=PaymentIntent.Origin.OPS_RECORDED,
                declared_xof=amount_xof,
                idempotency_key=idempotency_key,
                payload_hash=digest,
                declared_by=operator,
                **fields,
            )
            intent.status = get_gateway(channel.gateway).create_intent(intent=intent).status
            intent.save()
            _confirm(intent, operator=operator, received_xof=amount_xof)
            _audit(
                "payments.settlement.recorded",
                intent,
                operator,
                AuditEvent.ActorKind.OPS,
                amount_xof=amount_xof,
                channel=channel.slug,
                gateway=channel.gateway,
            )
            events.notify(events.WALLET_SETTLEMENT_CONFIRMED, [provider.owner], intent.public_id)
            wallet.notify_state_change(provider, before, provider_wallet(provider).state)
    except IntegrityError:
        if (existing := _replay(provider, idempotency_key, digest)) is not None:
            return CreatedIntent(existing, created=False)
        code = (
            "receipt_number_used" if fields.get("receipt_number") else "settlement_reference_used"
        )
        raise DomainError(code, status=409) from None
    return CreatedIntent(intent, created=True)


def _receipt_used(channel: SettlementChannel, receipt_number: str) -> bool:
    return (
        PaymentIntent.objects.filter(channel=channel, receipt_number=receipt_number)
        .exclude(status__in=PaymentIntent.CLOSED_WITHOUT_PAYMENT)
        .exists()
    )


# --- Surveillance ------------------------------------------------------------------------------


def watch_settlements(*, now: datetime | None = None) -> int:
    """Alerte l'Ops (une fois par heure au plus) si des déclarations attendent une décision
    depuis plus de ``WALLET_SETTLEMENT_REVIEW_SLA``. Renvoie leur nombre."""
    now = now or timezone.now()
    overdue = PaymentIntent.objects.filter(
        status__in=PaymentIntent.PENDING_STATUSES,
        created_at__lte=now - settings.WALLET_SETTLEMENT_REVIEW_SLA,
    ).count()
    if overdue:
        alert_once("wallet_settlements_overdue", 3600, "wallet_settlements_overdue", count=overdue)
    return overdue


# --- Données personnelles ----------------------------------------------------------------------


def deletion_blocker(user) -> str | None:
    """Un gérant dont le portefeuille n'est pas soldé (dette ou avoir) ou qui a une déclaration
    en attente ne supprime pas son compte (Q10). La dette naît dans la transaction où la
    réservation quitte ``ENGAGED`` (déjà bloquante) ; une déclaration naît sous le verrou du
    compte (``_lock_owner_and_provider``)."""
    provider = Provider.objects.filter(owner=user).first()
    if provider is None:
        return None
    wallet_now = provider_wallet(provider)
    pending = PaymentIntent.objects.filter(
        provider=provider, status__in=PaymentIntent.PENDING_STATUSES
    ).exists()
    if wallet_now.due_xof or wallet_now.credit_xof or pending:
        return "deletion_blocked_wallet_balance"
    return None


def anonymize_payments(user) -> None:
    """Anonymiseur : les 4 derniers chiffres du payeur sont effacés. Montants, références et
    écritures restent, pour la comptabilité (Q11), sans autre donnée que le lien au pro."""
    PaymentIntent.objects.filter(provider__owner=user).exclude(payer_last4="").update(
        payer_last4="", updated_at=timezone.now()
    )


def purge_payer_last4(*, now: datetime | None = None) -> int:
    """Efface les 4 derniers chiffres du payeur ``WALLET_PAYER_LAST4_RETENTION`` après la
    décision (ou le retrait). Renvoie le nombre de règlements purgés."""
    now = now or timezone.now()
    limit = now - settings.WALLET_PAYER_LAST4_RETENTION
    stale = PaymentIntent.objects.exclude(payer_last4="").filter(
        Q(decided_at__lte=limit)
        | Q(decided_at__isnull=True, status=Status.CANCELLED, updated_at__lte=limit)
    )
    count = stale.update(payer_last4="", updated_at=now)
    if count:
        audit(
            action="payments.payer_last4.purged",
            actor_kind=AuditEvent.ActorKind.SYSTEM,
            metadata={"count": count},
        )
    return count
