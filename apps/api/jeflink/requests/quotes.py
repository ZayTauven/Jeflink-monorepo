"""Devis (spec 003) : envoi, retrait, expiration, et effets de la réservation sur les devis.

Au plus 3 devis actifs par demande, comptés sous le verrou de la demande. Ordre des verrous,
partout : comptes, puis fiche pro, puis demande, puis réservation.
"""

import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import date, datetime

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from jeflink.common.dakar import dakar_today, period_bounds
from jeflink.common.errors import DomainError
from jeflink.common.pii import mask_numbers
from jeflink.notifications import events
from jeflink.providers.models import Provider
from jeflink.providers.services import count_masked_numbers
from jeflink.trust.services import audit

from .models import LABEL_MAX_LENGTH, MESSAGE_MAX_LENGTH, Quote, QuoteLine, ServiceRequest
from .services import IDEMPOTENCY_KEY, lock_request, transition_request

Status = Quote.Status
RequestStatus = ServiceRequest.Status

FIXED_DETAILS_MIN_MESSAGE = 20  # « Prix ferme » : une ligne de main-d'œuvre ou un vrai message


@dataclass(frozen=True)
class QuoteLineInput:
    kind: str
    amount_xof: int
    label: str = ""


@dataclass(frozen=True)
class QuoteInput:
    kind: str
    total_xof: int
    lines: tuple[QuoteLineInput, ...]
    slot_day: date
    slot_period: str
    message: str = ""
    visit_deductible: bool = False


@dataclass(frozen=True)
class CreatedQuote:
    quote: Quote
    created: bool  # False : même clé et même corps, le devis existant est rendu


def _payload_hash(request: ServiceRequest, content: QuoteInput) -> str:
    body = json.dumps(
        [
            str(request.public_id),
            content.kind,
            content.total_xof,
            [[line.kind, line.amount_xof, line.label] for line in content.lines],
            content.slot_day.isoformat(),
            content.slot_period,
            content.message,
            content.visit_deductible,
        ],
        ensure_ascii=False,
    )
    return hmac.new(settings.PII_HMAC_KEY.encode(), body.encode(), hashlib.sha256).hexdigest()


def _clean_content(content: QuoteInput, now: datetime) -> tuple[str, datetime, datetime]:
    """Contrôles sans accès à la base. Renvoie (message, début, fin du créneau)."""
    if content.kind not in Quote.Kind.values:
        raise DomainError("quote_total_invalid", status=422)
    lines = content.lines
    if not 1 <= len(lines) <= settings.QUOTE_MAX_LINES:
        raise DomainError("quote_total_invalid", status=422)
    for line in lines:
        if line.kind not in QuoteLine.Kind.values or line.amount_xof <= 0:
            raise DomainError("quote_total_invalid", status=422)
        if len(line.label.strip()) > LABEL_MAX_LENGTH:
            raise DomainError("text_too_long", status=422)
    total = sum(line.amount_xof for line in lines)
    if total != content.total_xof or not 0 < total <= settings.QUOTE_MAX_XOF:
        raise DomainError("quote_total_invalid", status=422)
    message = " ".join(content.message.split())
    if len(message) > MESSAGE_MAX_LENGTH:
        raise DomainError("text_too_long", status=422)
    if content.kind == Quote.Kind.VISIT:
        if total > settings.QUOTE_VISIT_MAX_XOF:
            raise DomainError("quote_total_invalid", status=422)
    else:
        has_labor = any(line.kind == QuoteLine.Kind.LABOR for line in lines)
        if not has_labor and len(message) < FIXED_DETAILS_MIN_MESSAGE:
            raise DomainError("quote_details_required", status=422)
    if content.slot_period not in settings.SLOT_PERIODS:
        raise DomainError("slot_invalid", status=422)
    today = dakar_today(now)
    if not 0 <= (content.slot_day - today).days <= settings.REQUEST_PREFERRED_MAX_DAYS:
        raise DomainError("slot_invalid", status=422)
    start, end = period_bounds(content.slot_day, content.slot_period)
    if start <= now:
        raise DomainError("slot_invalid", status=422)
    return message, start, end


def _active(request: ServiceRequest):
    return Quote.objects.filter(request=request, status__in=Quote.ACTIVE)


def _visible_to(request: ServiceRequest, provider: Provider) -> bool:
    return (
        request.trade_id in {t.pk for t in provider.trades.all()}
        and request.zone_id in {z.pk for z in provider.zones.all()}
        and not request.excluded_providers.filter(pk=provider.pk).exists()
    )


def submit_quote(
    *, provider: Provider, request: ServiceRequest, content: QuoteInput, idempotency_key: str
) -> CreatedQuote:
    """Un pro vérifié envoie un devis sur une demande qu'il a le droit de voir.

    Idempotent par ``(pro, idempotency_key)``. Refus : ``own_request``, ``request_closed``,
    ``quote_already_sent``, ``pro_quote_limit``, ``quotes_full`` (409), ``quote_total_invalid``,
    ``quote_details_required``, ``slot_invalid`` (422).
    """
    if not IDEMPOTENCY_KEY.match(idempotency_key or ""):
        raise DomainError("idempotency_key_required")
    digest = _payload_hash(request, content)
    existing = _replay(provider, idempotency_key, digest)
    if existing is not None:
        return CreatedQuote(existing, created=False)
    now = timezone.now()
    message, slot_start, slot_end = _clean_content(content, now)
    try:
        with transaction.atomic():
            quote = _insert(
                provider=provider,
                request=request,
                content=content,
                message=message,
                slot=(slot_start, slot_end),
                key=idempotency_key,
                digest=digest,
                now=now,
            )
    except IntegrityError as exc:
        # Course : même clé (la première gagne) ou deuxième devis actif du même pro.
        existing = _replay(provider, idempotency_key, digest)
        if existing is not None:
            return CreatedQuote(existing, created=False)
        raise DomainError("quote_already_sent", status=409) from exc
    return CreatedQuote(quote, created=True)


def _replay(provider: Provider, key: str, digest: str) -> Quote | None:
    existing = Quote.objects.filter(provider=provider, idempotency_key=key).first()
    if existing is None:
        return None
    if existing.payload_hash != digest:
        raise DomainError("idempotency_key_reused", status=409)
    return existing


def _insert(*, provider, request, content, message, slot, key, digest, now) -> Quote:
    provider = Provider.objects.select_for_update().get(pk=provider.pk)
    if provider.status != Provider.Status.VERIFIED:
        raise DomainError("provider_not_verified", status=403)
    request = lock_request(request)
    if request.client_id == provider.owner_id:
        raise DomainError("own_request", status=403)
    live = request.status in {RequestStatus.OPEN, RequestStatus.QUOTED}
    if not live or request.expires_at is None or request.expires_at <= now:
        raise DomainError("request_closed", status=409)
    if not _visible_to(request, provider):
        raise DomainError("not_found", status=404)
    if _active(request).filter(provider=provider).exists():
        raise DomainError("quote_already_sent", status=409)
    submitted = Quote.objects.filter(provider=provider, status=Status.SUBMITTED).count()
    if submitted >= settings.PRO_MAX_SUBMITTED_QUOTES:
        raise DomainError("pro_quote_limit", status=409)
    if _active(request).count() >= settings.QUOTE_MAX_ACTIVE:
        raise DomainError("quotes_full", status=409)

    ttl = settings.QUOTE_TTL_URGENT if request.urgent else settings.QUOTE_TTL
    quote = Quote.objects.create(
        request=request,
        provider=provider,
        kind=content.kind,
        total_xof=content.total_xof,
        visit_deductible=content.visit_deductible and content.kind == Quote.Kind.VISIT,
        message=message,
        slot_start=slot[0],
        slot_end=slot[1],
        valid_until=min(now + ttl, request.expires_at),
        idempotency_key=key,
        payload_hash=digest,
    )
    QuoteLine.objects.bulk_create(
        QuoteLine(
            quote=quote,
            position=index,
            kind=line.kind,
            label=" ".join(line.label.split()),
            amount_xof=line.amount_xof,
        )
        for index, line in enumerate(content.lines, start=1)
    )
    # Le contournement : un numéro dans le message ou une ligne est masqué à l'affichage ; on ne
    # compte que le nombre, jamais le texte.
    masked = mask_numbers(message)[1] + sum(mask_numbers(line.label)[1] for line in content.lines)
    count_masked_numbers(provider=provider, count=masked)
    if request.first_quoted_at is None:
        request.first_quoted_at = now
        request.save(update_fields=["first_quoted_at", "updated_at"])
    if request.status == RequestStatus.OPEN:
        transition_request(request, RequestStatus.QUOTED)
    audit(action="requests.quote.submitted", actor=provider.owner, target=quote,
          metadata={"kind": quote.kind})  # fmt: skip
    events.notify(events.QUOTE_RECEIVED, [request.client], request.public_id)
    return quote


def _sync_request(request: ServiceRequest) -> None:
    """Plus aucun devis en lice : la demande revient à ``open``. Demande verrouillée."""
    if request.status != RequestStatus.QUOTED:
        return
    waiting = request.quotes.filter(status__in=(Status.SUBMITTED, Status.HELD)).exists()
    if not waiting:
        transition_request(request, RequestStatus.OPEN)


@transaction.atomic
def withdraw_quote(*, quote: Quote, provider: Provider) -> Quote:
    """Le pro retire un devis ``submitted``. Libère une place ; la demande revient à ``open``
    s'il n'y en a plus d'autre."""
    request = lock_request(quote.request)
    quote = Quote.objects.select_for_update().get(pk=quote.pk)
    if quote.provider_id != provider.pk:
        raise DomainError("not_found", status=404)
    if provider.status != Provider.Status.VERIFIED:
        raise DomainError("provider_not_verified", status=403)
    if quote.status != Status.SUBMITTED:
        raise DomainError("quote_not_available", status=409)
    quote.status = Status.WITHDRAWN
    quote.save(update_fields=["status", "updated_at"])
    _sync_request(request)
    audit(action="requests.quote.withdrawn", actor=provider.owner, target=quote)
    return quote


def expire_quotes(*, now: datetime | None = None) -> int:
    """Expire les devis ``submitted`` échus ; la demande revient à ``open`` s'il n'en reste
    aucun. Idempotent. Renvoie le nombre de devis expirés."""
    now = now or timezone.now()
    due = Quote.objects.filter(status=Status.SUBMITTED, valid_until__lte=now)
    expired = 0
    for pk, request_id in list(due.values_list("pk", "request_id")):
        with transaction.atomic():
            request = ServiceRequest.objects.select_for_update().get(pk=request_id)
            quote = Quote.objects.select_for_update().get(pk=pk)
            if quote.status != Status.SUBMITTED or quote.valid_until > now:
                continue
            quote.status = Status.EXPIRED
            quote.save(update_fields=["status", "updated_at"])
            _sync_request(request)
            expired += 1
    return expired


# --- Effets d'une clôture ou d'une réservation sur les devis (demande verrouillée) -------------


def close_quotes(request: ServiceRequest, *, outcome: str) -> None:
    """La demande se ferme : ses devis en lice sont refusés (annulation) ou expirés."""
    if outcome not in {Status.DECLINED, Status.EXPIRED}:
        raise ValueError(f"issue de devis inconnue : {outcome}")
    request.quotes.filter(status__in=(Status.SUBMITTED, Status.HELD)).update(
        status=outcome, updated_at=timezone.now()
    )


def mark_accepted(*, quote: Quote, now: datetime) -> None:
    """Le client accepte ce devis : les autres attendent (``held``), la demande est réservée."""
    request = quote.request
    valid = (
        quote.status == Status.SUBMITTED
        and quote.valid_until > now
        and quote.slot_start > now
        and request.status == RequestStatus.QUOTED
        and request.expires_at is not None
        and request.expires_at > now
    )
    if not valid:
        raise DomainError("quote_not_available", status=409)
    quote.status = Status.ACCEPTED
    quote.save(update_fields=["status", "updated_at"])
    request.quotes.filter(status=Status.SUBMITTED).exclude(pk=quote.pk).update(
        status=Status.HELD, updated_at=now
    )
    transition_request(request, RequestStatus.BOOKED)


def decline_held(request: ServiceRequest) -> None:
    """Le pro a confirmé : les devis gardés en attente sont refusés."""
    request.quotes.filter(status=Status.HELD).update(
        status=Status.DECLINED, updated_at=timezone.now()
    )


def release_after_pro_cancel(
    *, request: ServiceRequest, quote: Quote, provider: Provider, now: datetime
) -> None:
    """Le pro (ou le système) annule : ses autres concurrents reviennent, il est exclu.

    Les devis gardés encore valides repassent à ``submitted`` (les autres expirent). La demande
    revient à ``quoted`` s'il en reste, sinon à ``open``, avec une nouvelle échéance.
    """
    quote.status = Status.WITHDRAWN
    quote.save(update_fields=["status", "updated_at"])
    held = request.quotes.filter(status=Status.HELD)
    held.filter(valid_until__gt=now).update(status=Status.SUBMITTED, updated_at=now)
    held.update(status=Status.EXPIRED, updated_at=now)
    request.excluded_providers.add(provider)
    back = (
        RequestStatus.QUOTED
        if request.quotes.filter(status=Status.SUBMITTED).exists()
        else RequestStatus.OPEN
    )
    transition_request(request, back)


def withdraw_for_provider(provider: Provider) -> int:
    """Suspension du pro : ses devis ``submitted`` sont retirés (acteur système)."""
    withdrawn = 0
    ids = Quote.objects.filter(provider=provider, status=Status.SUBMITTED)
    for request_id in set(ids.values_list("request_id", flat=True)):
        request = ServiceRequest.objects.select_for_update().get(pk=request_id)
        count = request.quotes.filter(provider=provider, status=Status.SUBMITTED).update(
            status=Status.WITHDRAWN, updated_at=timezone.now()
        )
        withdrawn += count
        _sync_request(request)
    return withdrawn
