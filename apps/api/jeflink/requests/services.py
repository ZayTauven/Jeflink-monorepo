"""Écritures de la demande (spec 003, ADR 0010) : seul ce module change son statut.

Repère, position, description et notes ne sont jamais écrits dans un log, un audit ou un message
d'erreur.
"""

import hashlib
import hmac
import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from jeflink.accounts.models import User
from jeflink.analytics.services import record_unserved
from jeflink.catalog.models import Service, Trade
from jeflink.common.dakar import dakar_today
from jeflink.common.errors import DomainError
from jeflink.common.ratelimit import Limit, RateLimitUnavailable, consume
from jeflink.notifications import events
from jeflink.trust.models import AuditEvent
from jeflink.trust.services import audit
from jeflink.zones.models import Zone
from jeflink.zones.selectors import availability

from .drafts import RequestDraft
from .models import (
    DESCRIPTION_MAX_LENGTH,
    LANDMARK_MAX_LENGTH,
    Quote,
    QuoteLine,
    ServiceRequest,
)
from .reasons import CLIENT_REASONS, check_reason
from .selectors import eligible_providers

Status = ServiceRequest.Status

# Statuts d'une réservation qui l'engagent encore (miroir de ``Booking.ENGAGED``, sans l'importer).
ENGAGED_BOOKING_STATUSES = (
    "accepted", "scheduled", "en_route", "on_site", "in_progress", "completed", "disputed",
)  # fmt: skip

IDEMPOTENCY_KEY = re.compile(r"^[A-Za-z0-9_-]{22,64}$")
_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")

# Table de transitions de la demande (ADR 0010). Tout autre couple est refusé.
TRANSITIONS: dict[str, frozenset[str]] = {
    Status.NEEDS_ZONE: frozenset({Status.OPEN, Status.CANCELLED}),
    Status.OPEN: frozenset({Status.QUOTED, Status.EXPIRED, Status.CANCELLED}),
    Status.QUOTED: frozenset({Status.OPEN, Status.BOOKED, Status.EXPIRED, Status.CANCELLED}),
    Status.BOOKED: frozenset({Status.QUOTED, Status.OPEN, Status.CANCELLED}),
    Status.EXPIRED: frozenset(),
    Status.CANCELLED: frozenset(),
}


@dataclass(frozen=True)
class CreatedRequest:
    request: ServiceRequest
    created: bool  # False : même clé et même corps, la demande existante est rendue


def lock_request(request: ServiceRequest) -> ServiceRequest:
    return ServiceRequest.objects.select_for_update().get(pk=request.pk)


def request_deadline(*, urgent: bool, now: datetime | None = None) -> datetime:
    """Échéance d'une demande qui passe en ``open`` : 72 h, ou 24 h si elle est urgente."""
    ttl = settings.REQUEST_TTL_URGENT if urgent else settings.REQUEST_TTL
    return (now or timezone.now()) + ttl


def dispatch_rank(*, urgent: bool, now: datetime) -> int:
    """Clé de tri de la diffusion : les urgentes d'abord, puis les plus anciennes (croissante)."""
    return (0 if urgent else 1) * 10**16 + int(now.timestamp() * 1_000_000)


def transition_request(request: ServiceRequest, to: str, *, reason: str = "") -> ServiceRequest:
    """Change le statut d'une demande **déjà verrouillée**, selon ``TRANSITIONS``.

    Ouverture (depuis ``needs_zone``) ou retour des devis après un désistement du pro : nouvelle
    échéance. Clôture
    (``expired``, ``cancelled``) : ``closed_at`` et ``close_reason``.
    """
    if to not in TRANSITIONS.get(request.status, frozenset()):
        raise DomainError("transition_not_allowed", status=409)
    now = timezone.now()
    previous = request.status
    request.status = to
    fields = ["status", "updated_at"]
    if to in {Status.OPEN, Status.QUOTED} and previous in {Status.NEEDS_ZONE, Status.BOOKED}:
        request.expires_at = request_deadline(urgent=request.urgent, now=now)
        fields.append("expires_at")
    if to in {Status.EXPIRED, Status.CANCELLED}:
        request.closed_at = now
        request.close_reason = reason[:24]
        fields += ["closed_at", "close_reason"]
    request.save(update_fields=fields)
    return request


# --- Création ---------------------------------------------------------------------------------


def _clean_text(value: str | None, *, max_length: int) -> str:
    text = _CONTROL.sub("", value or "").strip()
    if len(text) > max_length:
        raise DomainError("text_too_long", status=422)
    return text


def payload_hash(draft: RequestDraft, channel: str) -> str:
    """Empreinte du corps de la demande (HMAC) : repère et position n'y sont jamais en clair."""
    point = [draft.location.x, draft.location.y] if draft.location is not None else None
    body = json.dumps(
        [
            draft.trade_slug,
            draft.service_slug,
            draft.zone_slug,
            draft.zone_text,
            point,
            draft.landmark,
            draft.description,
            draft.urgent,
            draft.preferred_when,
            draft.preferred_date.isoformat() if draft.preferred_date else None,
            draft.preferred_period,
            channel,
        ],
        ensure_ascii=False,
    )
    return hmac.new(settings.PII_HMAC_KEY.encode(), body.encode(), hashlib.sha256).hexdigest()


def _replay(client: User, key: str, digest: str) -> ServiceRequest | None:
    existing = ServiceRequest.objects.filter(client=client, idempotency_key=key).first()
    if existing is None:
        return None
    if existing.payload_hash != digest:
        raise DomainError("idempotency_key_reused", status=409)
    return existing


def _check_draft(draft: RequestDraft, now: datetime) -> tuple[str, str]:
    """Contrôles sans accès à la base. Renvoie (repère, description) nettoyés."""
    landmark = _clean_text(draft.landmark, max_length=LANDMARK_MAX_LENGTH)
    description = _clean_text(draft.description, max_length=DESCRIPTION_MAX_LENGTH)
    if not landmark and draft.location is None:
        raise DomainError("landmark_or_location_required", status=422)
    if draft.location is not None and not (
        -90 <= draft.location.y <= 90 and -180 <= draft.location.x <= 180
    ):
        raise DomainError("location_invalid", status=422)
    if not (draft.zone_slug or (draft.zone_text or "").strip() or draft.location is not None):
        raise DomainError("zone_required", status=422)
    if draft.preferred_when not in ServiceRequest.When.values:
        raise DomainError("slot_invalid", status=422)
    if draft.preferred_period not in ServiceRequest.Period.values:
        raise DomainError("slot_invalid", status=422)
    if draft.preferred_when == ServiceRequest.When.DATE:
        today = dakar_today(now)
        limit = today + timedelta(days=settings.REQUEST_PREFERRED_MAX_DAYS)
        if draft.preferred_date is None or not today <= draft.preferred_date <= limit:
            raise DomainError("slot_invalid", status=422)
    return landmark, description


def _resolve_zone(draft: RequestDraft, channel: str):
    """Disponibilité du métier là où le client le demande ; signal « non servie » si refus."""
    if draft.zone_slug:
        result = availability(trade_slug=draft.trade_slug, zone_slug=draft.zone_slug)
    elif (draft.zone_text or "").strip():
        result = availability(trade_slug=draft.trade_slug, zone_text=draft.zone_text)
    else:
        result = availability(trade_slug=draft.trade_slug, point=draft.location)
    if result.status == "zone_ambiguous":
        candidates = [{"slug": zone.slug, "name": zone.name} for zone in result.candidates]
        raise DomainError("zone_ambiguous", status=422, candidates=candidates)
    if result.status in {"available", "zone_unknown"}:
        return result
    # Refus : le signal est écrit hors de la création (rien n'est annulé par le 422).
    zone_slug = result.zone.slug if result.zone else draft.zone_slug
    record_unserved(
        reason=result.status,
        channel=channel,
        trade_slug=draft.trade_slug,
        zone_slug=zone_slug,
        nearest_zone_slug=result.nearest_zone_slug,
        distance_km=result.distance_km,
    )
    raise DomainError(result.status, status=422)


def _resolve_service(draft: RequestDraft, trade_slug: str) -> Service | None:
    if not draft.service_slug:
        return None
    service = Service.objects.filter(
        trade__slug=trade_slug, slug=draft.service_slug, is_active=True
    ).first()
    if service is None:
        raise DomainError("service_not_in_trade", status=422)
    return service


def _check_rate(client: User) -> None:
    limit = Limit("request_create", settings.REQUEST_CREATE_DAILY_LIMIT, 24 * 3600)
    try:
        outcome = consume([(limit, str(client.public_id))])
    except RateLimitUnavailable as exc:
        # Jamais ouvert quand Redis tombe : créer des demandes en masse nuit aux pros.
        raise DomainError("rate_limit_unavailable", status=503) from exc
    if not outcome.allowed:
        raise DomainError("request_rate_limited", status=429, retry_after=outcome.retry_after)


def _live_count(client: User) -> int:
    return ServiceRequest.objects.filter(client=client, status__in=ServiceRequest.LIVE).count()


def create_request(
    *, client: User, draft: RequestDraft, channel: str, idempotency_key: str
) -> CreatedRequest:
    """Crée une demande (``open``, ou ``needs_zone`` si le quartier est inconnu).

    Idempotent par ``(client, idempotency_key)`` : même corps, même demande ; autre corps,
    ``409 idempotency_key_reused``. Une clé n'est retenue qu'après une création réussie : après un
    ``422`` (dont ``zone_ambiguous``), le client la rejoue avec le ``zone_slug`` choisi.

    Les refus de disponibilité écrivent un ``UnservedDemand`` hors de la transaction de création.
    """
    if not IDEMPOTENCY_KEY.match(idempotency_key or ""):
        raise DomainError("idempotency_key_required")
    if channel not in ServiceRequest.Channel.values:
        raise DomainError("channel_invalid")
    digest = payload_hash(draft, channel)
    existing = _replay(client, idempotency_key, digest)
    if existing is not None:
        return CreatedRequest(existing, created=False)

    now = timezone.now()
    landmark, description = _check_draft(draft, now)
    if _live_count(client) >= settings.REQUEST_MAX_OPEN_PER_CLIENT:
        raise DomainError("request_limit_reached", status=409)
    result = _resolve_zone(draft, channel)
    service = _resolve_service(draft, draft.trade_slug)
    if service is None and len(description) < 3:
        raise DomainError("description_required", status=422)
    _check_rate(client)

    try:
        with transaction.atomic():
            request = _insert(
                client=client,
                draft=draft,
                channel=channel,
                key=idempotency_key,
                digest=digest,
                landmark=landmark,
                description=description,
                service=service,
                result=result,
            )
    except IntegrityError:
        # Course sur la même clé : la première création gagne.
        existing = _replay(client, idempotency_key, digest)
        if existing is None:
            # Jamais le DETAIL de PostgreSQL (repère, position) : ni message, ni chaîne.
            raise DomainError("request_create_failed", status=500) from None
        return CreatedRequest(existing, created=False)
    return CreatedRequest(request, created=True)


def _insert(
    *, client, draft, channel, key, digest, landmark, description, service, result
) -> ServiceRequest:
    # Le compte est verrouillé : deux créations concurrentes ne dépassent pas la limite.
    locked = User.objects.select_for_update(no_key=True).get(pk=client.pk)
    if not locked.is_active or locked.is_deleted:
        raise DomainError("account_disabled", status=403)
    if _live_count(locked) >= settings.REQUEST_MAX_OPEN_PER_CLIENT:
        raise DomainError("request_limit_reached", status=409)
    trade = Trade.objects.get(slug=draft.trade_slug)
    urgent = draft.urgent if draft.urgent is not None else bool(service and service.urgent)
    asap = draft.preferred_when == ServiceRequest.When.ASAP
    needs_zone = result.status == "zone_unknown"
    now = timezone.now()
    request = ServiceRequest.objects.create(
        client=locked,
        trade=trade,
        service=service,
        zone=None if needs_zone else result.zone,
        zone_text=result.zone_text or "" if needs_zone else "",
        landmark=landmark,
        location=draft.location,
        description=description,
        urgent=urgent,
        preferred_when=draft.preferred_when,
        preferred_date=None if asap else draft.preferred_date,
        preferred_period=ServiceRequest.Period.ANY if asap else draft.preferred_period,
        dispatch_rank=dispatch_rank(urgent=urgent, now=now),
        status=Status.NEEDS_ZONE if needs_zone else Status.OPEN,
        expires_at=None if needs_zone else request_deadline(urgent=urgent, now=now),
        channel=channel,
        idempotency_key=key,
        payload_hash=digest,
    )
    audit(
        action="requests.request.created",
        actor=locked,
        target=request,
        metadata={"status": request.status, "channel": channel, "urgent": urgent},
    )
    if needs_zone:
        record_unserved(
            reason="zone_unknown",
            channel=channel,
            trade_slug=trade.slug,
            zone_text=result.zone_text or "",
        )
    elif not eligible_providers(request).exists():
        record_unserved(
            reason="no_provider",
            channel=channel,
            trade_slug=trade.slug,
            zone_slug=request.zone.slug,
        )
    else:
        notify_new_request(request)
    return request


def notify_new_request(request: ServiceRequest) -> None:
    """``request.new`` : les gérants des pros éligibles, après le commit. Aucune donnée perso."""
    owners = [provider.owner for provider in eligible_providers(request).select_related("owner")]
    events.notify(events.REQUEST_NEW, owners, request.public_id)


# --- Annulation, rattachement, expiration ----------------------------------------------------


@transaction.atomic
def cancel_request(
    *, request: ServiceRequest, actor: User, reason: str, note: str | None = None
) -> ServiceRequest:
    """Le client annule sa demande avant toute réservation, avec un motif.

    ``booked`` : il annule la réservation (``409 request_closed``), pas la demande.
    """
    request = lock_request(request)
    if request.client_id != actor.id:
        raise DomainError("not_found", status=404)
    clean = check_reason(reason, allowed=CLIENT_REASONS, note=note)
    if request.status not in {Status.NEEDS_ZONE, Status.OPEN, Status.QUOTED}:
        raise DomainError("request_closed", status=409)
    previous = request.status
    transition_request(request, Status.CANCELLED, reason=reason)
    _on_close(request, outcome=Quote.Status.DECLINED)
    audit(
        action="requests.request.cancelled",
        actor=actor,
        target=request,
        metadata={"from_status": previous, "reason": reason, "has_note": bool(clean)},
    )
    return request


@transaction.atomic
def attach_zone(*, request: ServiceRequest, zone: Zone, operator: User) -> ServiceRequest:
    """Ops : rattache à une zone une demande au quartier inconnu ; elle passe en ``open``."""
    request = lock_request(request)
    if request.status != Status.NEEDS_ZONE:
        raise DomainError("transition_not_allowed", status=409)
    if not (zone.is_active and zone.city.is_active):
        raise DomainError("zone_inactive", status=422)
    if not zone.trades.filter(pk=request.trade_id).exists():
        raise DomainError("trade_not_in_zone", status=422)
    request.zone = zone
    request.zone_text = ""
    request.save(update_fields=["zone", "zone_text", "updated_at"])
    transition_request(request, Status.OPEN, reason="zone_attached")
    audit(
        action="requests.request.zone_attached",
        actor=operator,
        actor_kind=AuditEvent.ActorKind.OPS,
        target=request,
        metadata={"zone_slug": zone.slug},
    )
    notify_new_request(request)
    return request


def release_after_client_cancel(*, request: ServiceRequest, reason: str) -> ServiceRequest:
    """Le client annule sa réservation : la demande est annulée et les devis en attente refusés.

    Appelée par ``bookings.services`` sur la demande **déjà verrouillée**.
    """
    transition_request(request, Status.CANCELLED, reason=reason)
    _on_close(request, outcome=Quote.Status.DECLINED)
    return request


def _on_close(request: ServiceRequest, *, outcome: str) -> None:
    """Effets d'une clôture sur les devis, sous le verrou de la demande : refusés si le client
    annule, expirés si la demande expire."""
    from . import quotes

    quotes.close_quotes(request, outcome=outcome)


def expire_due(*, now: datetime | None = None) -> int:
    """Expire les demandes ``open``/``quoted`` échues. Idempotent. Renvoie le nombre expiré."""
    now = now or timezone.now()
    due = ServiceRequest.objects.filter(
        status__in=(Status.OPEN, Status.QUOTED), expires_at__lte=now
    ).values_list("pk", flat=True)
    expired = 0
    for pk in list(due):
        with transaction.atomic():
            request = (
                ServiceRequest.objects.select_for_update(of=("self",))
                .select_related("trade", "zone")
                .get(pk=pk)
            )
            # Relue sous verrou : un devis accepté ou une annulation a pu passer entre-temps.
            if request.status not in {Status.OPEN, Status.QUOTED} or request.expires_at > now:
                continue
            never_quoted = request.first_quoted_at is None
            transition_request(request, Status.EXPIRED, reason="expired")
            _on_close(request, outcome=Quote.Status.EXPIRED)
            if never_quoted:
                record_unserved(
                    reason="no_quote",
                    channel=request.channel,
                    trade_slug=request.trade.slug,
                    zone_slug=request.zone.slug if request.zone else None,
                )
            expired += 1
    return expired


# --- Données personnelles ---------------------------------------------------------------------


def purge_locations(*, now: datetime | None = None) -> int:
    """Vide repère et position 30 jours après une demande expirée ou annulée sans réservation."""
    now = now or timezone.now()
    cutoff = now - timedelta(days=settings.REQUEST_LOCATION_RETENTION_DAYS)
    return (
        ServiceRequest.objects.filter(
            status__in=(Status.EXPIRED, Status.CANCELLED),
            closed_at__lte=cutoff,
            # Une demande qui a eu une réservation garde ses données jusqu'à la durée fixée à
            # l'étape 4 (garantie, litiges).
            bookings__isnull=True,
        )
        .exclude(landmark="", location__isnull=True)
        .update(landmark="", location=None, updated_at=now)
    )


def clear_contact(request_ids: list[int]) -> int:
    """Vide repère et position de ces demandes (point laissé ouvert par la spec 003 : 90 jours
    après la clôture de la réservation, appelé par ``bookings``). Idempotent."""
    return (
        ServiceRequest.objects.filter(pk__in=request_ids)
        .exclude(landmark="", location__isnull=True)
        .update(landmark="", location=None, updated_at=timezone.now())
    )


@transaction.atomic
def anonymize_requests(user: User) -> None:
    """Anonymiseur : annule les demandes ouvertes (devis refusés) et vide les données perso.

    Une demande ``booked`` dont la réservation est engagée ne peut pas exister ici (elle bloque
    la suppression). Une demande ``booked`` dont la réservation est close ou annulée est vidée.
    """
    for request in ServiceRequest.objects.select_for_update().filter(client=user):
        if request.status in {Status.NEEDS_ZONE, Status.OPEN, Status.QUOTED}:
            transition_request(request, Status.CANCELLED, reason="account_deleted")
            _on_close(request, outcome=Quote.Status.DECLINED)
        if (
            request.status == Status.BOOKED
            and request.bookings.filter(status__in=ENGAGED_BOOKING_STATUSES).exists()
        ):
            continue  # mission engagée : le blocage de suppression l'interdit déjà
        request.landmark = ""
        request.description = ""
        request.zone_text = ""
        request.location = None
        request.save(
            update_fields=["landmark", "description", "zone_text", "location", "updated_at"]
        )
    # Un pro qui supprime son compte : ses messages et libellés de devis sont effacés.
    Quote.objects.filter(provider__owner=user).update(message="")
    QuoteLine.objects.filter(quote__provider__owner=user).update(label="")
