"""Écritures des réservations (spec 003 et 004, ADR 0010). Seul ce module écrit
``Booking.status`` (et, à partir des avenants, ``Booking.amount_xof``).

Ordre des verrous, partout : comptes (par id), fiche pro, demande, réservation. La note d'un
motif « autre » n'est jamais écrite dans un log ni dans un audit.
"""

import hashlib
import hmac
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Exists, OuterRef, Q
from django.utils import timezone

from jeflink.accounts.models import User
from jeflink.common import crypto, storage
from jeflink.common.errors import DomainError
from jeflink.common.images import InvalidImage, reencode
from jeflink.notifications import events
from jeflink.providers.models import Provider
from jeflink.requests import quotes as quote_services
from jeflink.requests import services as request_services
from jeflink.requests.models import Quote, QuoteLine, ServiceRequest
from jeflink.requests.quotes import QuoteLineInput
from jeflink.requests.reasons import CLIENT_REASONS, PRO_REASONS, check_reason, clean_note
from jeflink.trust import services as trust_services
from jeflink.trust.models import AuditEvent, Dispute
from jeflink.trust.services import audit

from .machine import (
    ALWAYS_LATE_FROM,
    CLIENT_ABSENT,
    DECLARED,
    NO_SHOW_WEIGHT,
    PRO_NO_SHOW,
    Actor,
    Status,
    confirm_deadline,
    is_late,
    reliability_weight,
)
from .models import Amendment, AmendmentLine, Booking, BookingEvent, BookingPhoto, NoShowReport

# Clés permises dans ``BookingEvent.metadata`` (schéma fermé). Jamais de texte libre, de numéro,
# de code de fin ni de position.
EVENT_METADATA_KEYS = frozenset(
    {
        "late",
        "reliability_weight",
        "chained",
        "occurred_at",
        "amendment",
        "photos_pending",
        "completion_method",
        "dispute_decision",
    }
)
# Colonnes qu'une transition peut écrire avec le statut (même verrou, même transaction).
TRANSITION_FIELDS = frozenset({"amount_xof", "completion_method", "no_code_reason"})
# Horodatage posé à l'arrivée dans un statut.
_STAMPS = {
    Status.EN_ROUTE: "en_route_at",
    Status.ON_SITE: "on_site_at",
    Status.COMPLETED: "completed_at",
    Status.CLOSED: "closed_at",
}

# Appelés dans la transaction de toute arrivée à ``closed``, avec ``(booking, reason)``.
CloseHandler = Callable[[Booking, str], None]
_CLOSE_HANDLERS: list[CloseHandler] = []


def register_close_handler(handler: CloseHandler) -> None:
    """Point d'accroche de la clôture (étape 5 : commission ; ``reviews`` : publication).

    Le gestionnaire s'exécute dans la transaction de ``transition()``, réservation verrouillée,
    et doit être idempotent par réservation. Appelé dans le ``ready()`` d'un domaine.
    """
    if handler not in _CLOSE_HANDLERS:
        _CLOSE_HANDLERS.append(handler)


@dataclass(frozen=True)
class CreatedBooking:
    booking: Booking
    created: bool  # False : le devis était déjà accepté, la réservation existante est rendue


# --- Journal et transition --------------------------------------------------------------------


def _write_event(
    booking: Booking,
    *,
    from_status: str,
    to: str,
    actor: User | None,
    actor_kind: str,
    reason: str,
    note: str,
    metadata: dict,
) -> BookingEvent:
    if set(metadata) - EVENT_METADATA_KEYS:
        raise ValueError("métadonnées d'événement hors schéma")
    return BookingEvent.objects.create(
        booking=booking,
        from_status=from_status,
        to_status=to,
        actor=actor if actor_kind != Actor.SYSTEM else None,
        actor_kind=actor_kind,
        reason=reason[:24],
        note=note,
        metadata=metadata,
    )


def transition(
    booking: Booking,
    *,
    to: str,
    actor: User | None,
    actor_kind: str,
    reason: str,
    note: str = "",
    metadata: dict | None = None,
    fields: dict | None = None,
) -> Booking:
    """Seul point de changement du statut d'une réservation.

    Verrouille la ligne, vérifie le couple (``transition_not_allowed`` s'il est interdit,
    ``transition_not_enabled`` s'il est déclaré mais pas activé) et l'acteur, écrit le statut, son
    horodatage puis un ``BookingEvent``. À appeler dans une transaction.

    ``metadata`` s'ajoute à celle de l'événement (schéma fermé) ; ``fields`` écrit d'autres
    colonnes (``TRANSITION_FIELDS``) avec le statut. Arriver à ``closed`` appelle les
    gestionnaires de clôture, dans la même transaction.
    """
    booking = Booking.objects.select_for_update().get(pk=booking.pk)
    rule = DECLARED.get((booking.status, to))
    if rule is None or actor_kind not in rule.actors:
        raise DomainError("transition_not_allowed", status=409)
    if not rule.enabled:
        raise DomainError("transition_not_enabled", status=409)
    if set(fields or {}) - TRANSITION_FIELDS:
        raise ValueError("colonne hors de la liste des transitions")
    now = timezone.now()
    event_metadata: dict = dict(metadata or {})
    previous = booking.status
    update = ["status", "updated_at"]
    if to == Status.CANCELLED:
        late = previous in ALWAYS_LATE_FROM or (
            previous == Status.SCHEDULED and is_late(slot_start=booking.slot_start, now=now)
        )
        event_metadata |= {
            "late": late,
            "reliability_weight": reliability_weight(
                actor_kind=actor_kind, from_status=previous, to_status=to, late=late, reason=reason
            ),
        }
        booking.cancelled_by = actor_kind
        booking.cancel_reason = reason[:24]
        update += ["cancelled_by", "cancel_reason"]
    if previous != to and to in _STAMPS:
        setattr(booking, _STAMPS[to], now)
        update.append(_STAMPS[to])
    if to == Status.SCHEDULED:
        booking.completion_code_enc = crypto.encrypt(generate_completion_code())
        update.append("completion_code_enc")
    if to in {Status.COMPLETED, Status.CANCELLED}:
        booking.completion_code_enc = ""  # le code n'a plus d'usage
        update.append("completion_code_enc")
    if previous == Status.ON_SITE and to == Status.IN_PROGRESS:
        booking.started_at = now
        update.append("started_at")
    if to == Status.COMPLETED:
        no_code = (fields or {}).get("completion_method") == Booking.CompletionMethod.NO_CODE
        window = (
            settings.BOOKING_DISPUTE_WINDOW_NO_CODE if no_code else settings.BOOKING_DISPUTE_WINDOW
        )
        booking.dispute_deadline = now + window
        update.append("dispute_deadline")
    for name, value in (fields or {}).items():
        setattr(booking, name, value)
        update.append(name)
    booking.status = to
    booking.save(update_fields=update)
    _write_event(
        booking,
        from_status=previous,
        to=to,
        actor=actor,
        actor_kind=actor_kind,
        reason=reason,
        note=note,
        metadata=event_metadata,
    )
    if to == Status.CLOSED:
        for handler in tuple(_CLOSE_HANDLERS):
            handler(booking, reason)
    return booking


# --- Création : le client accepte un devis ----------------------------------------------------


def _lock_accounts(actor: User, *others: User) -> dict[int, User]:
    """Verrouille les comptes dans l'ordre des id (jamais d'interblocage) et les relit."""
    locked = {
        user.pk: user
        for user in User.objects.select_for_update(no_key=True)
        .filter(pk__in={u.pk for u in (actor, *others)})
        .order_by("pk")
    }
    for user in locked.values():
        if not user.is_active or user.is_deleted:
            # Le compte d'un tiers (le pro) ne se révèle pas : devis indisponible.
            if user.pk != actor.pk:
                raise DomainError("quote_not_available", status=409)
            raise DomainError("account_disabled", status=403)
    return locked


def create_from_quote(*, quote: Quote, actor: User) -> CreatedBooking:
    """Le client accepte un devis : la réservation naît à ``accepted``.

    Idempotent : un devis déjà accepté par ce client rend sa réservation (``created=False``).
    Deux acceptations simultanées donnent une seule réservation (verrou de la demande).
    Refus : ``quote_not_available`` (devis pris, expiré, retiré, créneau passé, pro suspendu).
    """
    try:
        with transaction.atomic():
            return _create_from_quote(quote=quote, actor=actor)
    except IntegrityError:
        # Course sur la contrainte « une réservation active par demande » : la première gagne.
        existing = Booking.objects.filter(quote=quote, client=actor).first()
        if existing is None:
            raise DomainError("quote_not_available", status=409) from None
        return CreatedBooking(existing, created=False)


def _create_from_quote(*, quote: Quote, actor: User) -> CreatedBooking:
    provider_ref = quote.provider
    # 1. comptes, 2. fiche pro, 3. demande : l'ordre commun à tout le domaine.
    accounts = _lock_accounts(actor, provider_ref.owner)
    provider = Provider.objects.select_for_update().get(pk=provider_ref.pk)
    request = request_services.lock_request(quote.request)
    quote = Quote.objects.select_for_update().get(pk=quote.pk)
    quote.request = request
    if request.client_id != actor.id:
        raise DomainError("not_found", status=404)
    existing = Booking.objects.filter(quote=quote).first()
    if existing is not None:
        # Rejeu : même client, même devis. Une réservation annulée n'est plus rejouable.
        if existing.status == Status.CANCELLED:
            raise DomainError("quote_not_available", status=409)
        return CreatedBooking(existing, created=False)
    if provider.status != Provider.Status.VERIFIED:
        raise DomainError("quote_not_available", status=409)
    now = timezone.now()
    quote_services.mark_accepted(quote=quote, now=now)  # devis, autres devis, demande
    booking = Booking.objects.create(
        request=request,
        quote=quote,
        client=accounts[actor.pk],
        provider=provider,
        amount_xof=quote.total_xof,
        original_amount_xof=quote.total_xof,
        slot_start=quote.slot_start,
        slot_end=quote.slot_end,
        confirm_deadline=confirm_deadline(
            accepted_at=now, slot_start=quote.slot_start, urgent=request.urgent
        ),
    )
    # Création : l'événement initial passe par la même fonction que ``transition()``.
    _write_event(
        booking,
        from_status="",
        to=Status.ACCEPTED,
        actor=actor,
        actor_kind=Actor.CLIENT,
        reason="quote_accepted",
        note="",
        metadata={},
    )
    audit(action="bookings.booking.created", actor=actor, target=booking,
          metadata={"urgent": request.urgent})  # fmt: skip
    events.notify(events.BOOKING_TO_CONFIRM, [accounts[provider.owner_id]], booking.public_id)
    return CreatedBooking(booking, created=True)


# --- Confirmation par le pro ------------------------------------------------------------------


def _lock_for_booking(booking: Booking) -> tuple[Provider, ServiceRequest, Booking]:
    provider = Provider.objects.select_for_update().get(pk=booking.provider_id)
    request = request_services.lock_request(booking.request)
    booking = Booking.objects.select_for_update().get(pk=booking.pk)
    return provider, request, booking


def confirm_booking(*, booking: Booking, actor: User) -> Booking:
    """Le pro confirme (``accepted`` → ``scheduled``) : les devis gardés en attente sont refusés.

    Une confirmation après l'échéance annule la réservation (``pro_unconfirmed``) et répond
    ``409 transition_not_allowed`` : un retard de la tâche d'annulation ne la ressuscite pas.
    """
    with transaction.atomic():
        provider, request, booking = _lock_for_booking(booking)
        if provider.owner_id != actor.id:
            raise DomainError("not_found", status=404)
        if provider.status != Provider.Status.VERIFIED:
            raise DomainError("provider_not_verified", status=403)
        if booking.status != Status.ACCEPTED:
            raise DomainError("transition_not_allowed", status=409)
        overdue = timezone.now() >= booking.confirm_deadline
        if overdue:
            _cancel(booking, request, provider, actor=None, actor_kind=Actor.SYSTEM,
                    reason="pro_unconfirmed")  # fmt: skip
        else:
            transition(booking, to=Status.SCHEDULED, actor=actor, actor_kind=Actor.PRO,
                       reason="confirmed")  # fmt: skip
            quote_services.decline_held(request)
            audit(action="bookings.booking.confirmed", actor=actor, target=booking)
            events.notify(events.BOOKING_SCHEDULED, [booking.client], booking.public_id)
    if overdue:
        raise DomainError("transition_not_allowed", status=409)
    booking.refresh_from_db()
    return booking


# --- Déroulé de l'intervention : en route, sur place, début (spec 004) ---------------------------

# Statuts à partir desquels une action du pro est déjà faite : la rejouer renvoie l'état courant.
_PAST_EN_ROUTE = (
    Status.EN_ROUTE, Status.ON_SITE, Status.IN_PROGRESS, Status.COMPLETED, Status.DISPUTED,
    Status.CLOSED,
)  # fmt: skip
_PAST_ON_SITE = _PAST_EN_ROUTE[1:]
_PAST_START = _PAST_ON_SITE[1:]


def _lock_for_pro(booking: Booking, actor: User, *, verified: bool) -> Booking:
    """Verrous (fiche, demande, réservation) puis contrôle du gérant. ``verified=False`` pour les
    écritures qu'un pro suspendu garde le droit de faire sur une intervention en cours."""
    provider, _, booking = _lock_for_booking(booking)
    if provider.owner_id != actor.id:
        raise DomainError("not_found", status=404)
    if verified and provider.status != Provider.Status.VERIFIED:
        raise DomainError("provider_not_verified", status=403)
    return booking


def check_occurred_at(booking: Booking, occurred_at: datetime | None, *, now: datetime) -> None:
    """Heure de l'appareil, gardée en métadonnée : 24 h avant au plus, jamais dans le futur ni
    avant l'événement précédent. L'heure du serveur fait foi (``422 occurred_at_invalid``)."""
    if occurred_at is None:
        return
    previous = booking.events.order_by("-id").values_list("created_at", flat=True).first()
    too_old = occurred_at < now - settings.OCCURRED_AT_MAX_SKEW
    if occurred_at > now or too_old or (previous is not None and occurred_at < previous):
        raise DomainError("occurred_at_invalid", status=422)


def _occurred(occurred_at: datetime | None) -> dict:
    return {"occurred_at": occurred_at.isoformat()} if occurred_at else {}


def _progress(
    booking: Booking, actor: User, *, to: str, chained: bool = False, metadata: dict | None = None
) -> Booking:
    previous = booking.status
    meta = {**(metadata or {}), **({"chained": True} if chained else {})}
    booking = transition(
        booking, to=to, actor=actor, actor_kind=Actor.PRO, reason=to, metadata=meta
    )
    audit(
        action="bookings.booking.progressed",
        actor=actor,
        target=booking,
        metadata={"from_status": previous, "to_status": to, "chained": chained},
    )
    if to == Status.EN_ROUTE:
        _send_code_sms(booking, automatic=True)
    return booking


@transaction.atomic
def mark_en_route(*, booking: Booking, actor: User, occurred_at: datetime | None = None) -> Booking:
    """Le pro part (``scheduled`` → ``en_route``). Rejouée une fois partie : état courant, sans
    événement. Notifie le client (le SMS du code de fin part ici, spec 004)."""
    booking = _lock_for_pro(booking, actor, verified=True)
    if booking.status in _PAST_EN_ROUTE:
        return booking
    if booking.status != Status.SCHEDULED:
        raise DomainError("transition_not_allowed", status=409)
    check_occurred_at(booking, occurred_at, now=timezone.now())
    booking = _progress(booking, actor, to=Status.EN_ROUTE, metadata=_occurred(occurred_at))
    events.notify(events.BOOKING_PROGRESS, [booking.client], booking.public_id)
    return booking


@transaction.atomic
def mark_arrived(*, booking: Booking, actor: User, occurred_at: datetime | None = None) -> Booking:
    """Le pro est sur place (``en_route`` → ``on_site``). Depuis ``scheduled``, l'étape manquée
    est rattrapée : deux transitions, deux événements marqués ``chained``."""
    booking = _lock_for_pro(booking, actor, verified=True)
    if booking.status in _PAST_ON_SITE:
        return booking
    if booking.status not in {Status.SCHEDULED, Status.EN_ROUTE}:
        raise DomainError("transition_not_allowed", status=409)
    check_occurred_at(booking, occurred_at, now=timezone.now())
    chained = booking.status == Status.SCHEDULED
    if chained:
        booking = _progress(booking, actor, to=Status.EN_ROUTE, chained=True)
    booking = _progress(
        booking, actor, to=Status.ON_SITE, chained=chained, metadata=_occurred(occurred_at)
    )
    events.notify(events.BOOKING_PROGRESS, [booking.client], booking.public_id)
    return booking


def has_photos(booking: Booking, phase: str) -> bool:
    """Une photo visible de la phase est-elle arrivée ?"""
    return BookingPhoto.objects.visible().filter(booking=booking, phase=phase).exists()


@transaction.atomic
def start_work(
    *,
    booking: Booking,
    actor: User,
    photos_pending: bool = False,
    occurred_at: datetime | None = None,
) -> Booking:
    """Le pro commence (``on_site`` → ``in_progress``), jamais déduit d'une étape manquée.

    Exige une photo « avant » ou ``photos_pending`` (la file de l'appareil les enverra) :
    ``422 before_photos_required``.
    """
    booking = _lock_for_pro(booking, actor, verified=True)
    if booking.status in _PAST_START:
        return booking
    if booking.status != Status.ON_SITE:
        raise DomainError("transition_not_allowed", status=409)
    if not (photos_pending or has_photos(booking, "before")):
        raise DomainError("before_photos_required", status=422)
    check_occurred_at(booking, occurred_at, now=timezone.now())
    meta = _occurred(occurred_at) | ({"photos_pending": True} if photos_pending else {})
    booking = _progress(booking, actor, to=Status.IN_PROGRESS, metadata=meta)
    events.notify(events.BOOKING_PROGRESS, [booking.client], booking.public_id)
    return booking


# --- Clôture : fin de la fenêtre de contestation (spec 004) ---------------------------------------


def close_due(*, now: datetime | None = None) -> int:
    """Clôt les réservations ``completed`` dont ``dispute_deadline`` est passée (motif
    ``window_elapsed``) et appelle les gestionnaires de clôture. Idempotent."""
    now = now or timezone.now()
    due = Booking.objects.filter(status=Status.COMPLETED, dispute_deadline__lte=now)
    closed = 0
    for booking in list(due.select_related("provider")):
        with transaction.atomic():
            provider, _, locked = _lock_for_booking(booking)
            # Relue sous verrou : le client a pu contester entre-temps.
            if (
                locked.status != Status.COMPLETED
                or locked.dispute_deadline is None
                or locked.dispute_deadline > now
            ):
                continue
            transition(
                locked, to=Status.CLOSED, actor=None, actor_kind=Actor.SYSTEM,
                reason="window_elapsed",
            )  # fmt: skip
            audit(
                action="bookings.booking.closed",
                actor_kind=AuditEvent.ActorKind.SYSTEM,
                target=locked,
                metadata={"reason": "window_elapsed"},
            )
            events.notify(events.BOOKING_CLOSED, [locked.client, provider.owner], locked.public_id)
            closed += 1
    return closed


def remind_disputes(*, now: datetime | None = None) -> int:
    """Rappelle au client, une seule fois, que la fenêtre de contestation se ferme bientôt."""
    now = now or timezone.now()
    due = Booking.objects.filter(
        status=Status.COMPLETED,
        dispute_reminder_sent_at__isnull=True,
        dispute_deadline__gt=now,
        dispute_deadline__lte=now + settings.BOOKING_DISPUTE_REMINDER,
    )
    sent = 0
    for pk in list(due.values_list("pk", flat=True)):
        with transaction.atomic():
            locked = Booking.objects.select_for_update().select_related("client").get(pk=pk)
            if locked.status != Status.COMPLETED or locked.dispute_reminder_sent_at:
                continue
            locked.dispute_reminder_sent_at = now
            locked.save(update_fields=["dispute_reminder_sent_at", "updated_at"])
            events.notify(events.DISPUTE_REMINDER, [locked.client], locked.public_id)
            sent += 1
    return sent


# --- Avenants (spec 004) -------------------------------------------------------------------------


@dataclass(frozen=True)
class CreatedAmendment:
    amendment: Amendment
    created: bool  # False : même clé et même corps, l'avenant existant est rendu


def change_pct(amendment: Amendment) -> int:
    """Écart en % (signé, arrondi) entre l'ancien et le nouveau prix."""
    delta = amendment.total_xof - amendment.previous_amount_xof
    return round(delta * 100 / amendment.previous_amount_xof)


def requires_confirmation(amendment: Amendment) -> bool:
    """Une hausse au-delà du seuil demande une confirmation de plus ; une baisse, aucune."""
    delta = amendment.total_xof - amendment.previous_amount_xof
    # Comparaison exacte en entiers (pas sur le pourcentage arrondi affiché).
    return delta * 100 > settings.AMENDMENT_CONFIRM_THRESHOLD_PCT * amendment.previous_amount_xof


def _amendment_hash(reason: str, note: str, total: int, lines: tuple[QuoteLineInput, ...]) -> str:
    body = repr((reason, note, total, [(ln.kind, ln.amount_xof, ln.label) for ln in lines]))
    return hmac.new(settings.PII_HMAC_KEY.encode(), body.encode(), hashlib.sha256).hexdigest()


def _check_amendment(
    booking: Booking, reason: str, note: str, total: int, lines: tuple[QuoteLineInput, ...]
) -> str:
    """Contrôles sans verrou. Renvoie la note nettoyée."""
    if reason not in Amendment.Reason.values:
        raise DomainError("amendment_reason_invalid", status=422)
    clean = clean_note(note)  # 422 note_invalid : numéros refusés, 200 caractères
    if reason == Amendment.Reason.OTHER and not clean:
        raise DomainError("note_invalid", status=422)
    if not 1 <= len(lines) <= settings.QUOTE_MAX_LINES:
        raise DomainError("amendment_total_invalid", status=422)
    for line in lines:
        if line.kind not in QuoteLine.Kind.values or line.amount_xof <= 0:
            raise DomainError("amendment_total_invalid", status=422)
        if len(line.label.strip()) > 60:
            raise DomainError("text_too_long", status=422)
    if sum(line.amount_xof for line in lines) != total or not 0 < total <= settings.QUOTE_MAX_XOF:
        raise DomainError("amendment_total_invalid", status=422)
    return clean


def propose_amendment(
    *,
    booking: Booking,
    actor: User,
    reason: str,
    note: str,
    lines: tuple[QuoteLineInput, ...],
    total_xof: int,
    idempotency_key: str,
) -> CreatedAmendment:
    """Le pro propose le nouveau prix complet d'une intervention ``in_progress``.

    Refus : ``422 amendment_total_invalid`` (somme des lignes, ``0 < total ≤ QUOTE_MAX_XOF``,
    total égal au montant courant), ``amendment_reason_invalid``, ``note_invalid`` ;
    ``409 amendment_pending`` (un seul en attente), ``amendment_limit`` (3 par réservation),
    ``transition_not_allowed`` (hors ``in_progress``), ``idempotency_key_reused``. Le client est
    prévenu par SMS (ancien et nouveau prix).
    """
    if not request_services.IDEMPOTENCY_KEY.match(idempotency_key or ""):
        raise DomainError("idempotency_key_required")
    clean = _check_amendment(booking, reason, note, total_xof, lines)
    digest = _amendment_hash(reason, clean, total_xof, lines)
    try:
        with transaction.atomic():
            return _insert_amendment(
                booking, actor, reason, clean, total_xof, lines, idempotency_key, digest
            )
    except IntegrityError:
        # Course : même clé (la première gagne) ou deuxième avenant en attente.
        existing = Amendment.objects.filter(
            booking=booking, idempotency_key=idempotency_key
        ).first()
        if existing is not None and existing.payload_hash == digest:
            return CreatedAmendment(existing, created=False)
        raise DomainError("amendment_pending", status=409) from None


def _insert_amendment(
    booking, actor, reason, note, total_xof, lines, key, digest
) -> CreatedAmendment:
    booking = _lock_for_pro(booking, actor, verified=True)
    existing = Amendment.objects.filter(booking=booking, idempotency_key=key).first()
    if existing is not None:
        if existing.payload_hash != digest:
            raise DomainError("idempotency_key_reused", status=409)
        return CreatedAmendment(existing, created=False)
    if booking.status != Status.IN_PROGRESS:
        raise DomainError("transition_not_allowed", status=409)
    if total_xof == booking.amount_xof:
        raise DomainError("amendment_total_invalid", status=422)
    existing_all = Amendment.objects.filter(booking=booking)
    if existing_all.filter(status=Amendment.Status.PROPOSED).exists():
        raise DomainError("amendment_pending", status=409)
    if existing_all.count() >= settings.BOOKING_AMENDMENTS_MAX:
        raise DomainError("amendment_limit", status=409)
    amendment = Amendment.objects.create(
        booking=booking,
        reason=reason,
        note=note,
        previous_amount_xof=booking.amount_xof,
        total_xof=total_xof,
        idempotency_key=key,
        payload_hash=digest,
    )
    AmendmentLine.objects.bulk_create(
        AmendmentLine(
            amendment=amendment,
            position=index,
            kind=line.kind,
            label=" ".join(line.label.split()),
            amount_xof=line.amount_xof,
        )
        for index, line in enumerate(lines, start=1)
    )
    audit(
        action="bookings.amendment.proposed",
        actor=actor,
        target=amendment,
        metadata={
            "previous_xof": amendment.previous_amount_xof,
            "total_xof": amendment.total_xof,
            "reason": reason,
        },
    )
    events.notify(events.AMENDMENT_PROPOSED, [booking.client], booking.public_id)
    return CreatedAmendment(amendment, created=True)


def _lock_amendment(amendment: Amendment) -> tuple[Booking, Amendment]:
    """Verrous dans l'ordre commun (fiche, demande, réservation), puis l'avenant."""
    _, _, booking = _lock_for_booking(amendment.booking)
    return booking, Amendment.objects.select_for_update().get(pk=amendment.pk)


@transaction.atomic
def withdraw_amendment(*, amendment: Amendment, actor: User) -> Amendment:
    """Le pro retire son avenant en attente. Rejoué : l'état courant ; ``409
    amendment_not_pending`` si le client a déjà décidé."""
    booking, amendment = _lock_amendment(amendment)
    provider = Provider.objects.get(pk=booking.provider_id)
    if provider.owner_id != actor.id:
        raise DomainError("not_found", status=404)
    if provider.status != Provider.Status.VERIFIED:
        raise DomainError("provider_not_verified", status=403)
    if amendment.status == Amendment.Status.WITHDRAWN:
        return amendment
    if amendment.status != Amendment.Status.PROPOSED:
        raise DomainError("amendment_not_pending", status=409)
    _close_amendment(amendment, Amendment.Status.WITHDRAWN)
    audit(action="bookings.amendment.withdrawn", actor=actor, target=amendment)
    return amendment


def _close_amendment(amendment: Amendment, status: str) -> None:
    amendment.status = status
    amendment.decided_at = timezone.now()
    amendment.save(update_fields=["status", "decided_at", "updated_at"])


def _lapse_amendments(booking: Booking) -> None:
    """``complete`` rend caduc un avenant encore en attente (réservation déjà verrouillée)."""
    Amendment.objects.filter(booking=booking, status=Amendment.Status.PROPOSED).update(
        status=Amendment.Status.LAPSED, decided_at=timezone.now(), updated_at=timezone.now()
    )


def _decide_amendment(*, amendment: Amendment, actor: User, accept: bool) -> Booking:
    booking, amendment = _lock_amendment(amendment)
    if booking.client_id != actor.id:
        raise DomainError("not_found", status=404)
    done = Amendment.Status.ACCEPTED if accept else Amendment.Status.DECLINED
    if amendment.status == done:
        return booking  # rejeu
    if amendment.status != Amendment.Status.PROPOSED:
        raise DomainError("amendment_not_pending", status=409)
    if booking.status != Status.IN_PROGRESS:
        raise DomainError("transition_not_allowed", status=409)
    provider_owner = Provider.objects.select_related("owner").get(pk=booking.provider_id).owner
    if accept:
        # Le seul endroit où ``amount_xof`` change : session du client, sous verrou.
        booking = transition(
            booking, to=Status.IN_PROGRESS, actor=actor, actor_kind=Actor.CLIENT,
            reason="amendment_accepted",
            metadata={
                "amendment": {
                    "public_id": str(amendment.public_id),
                    "previous_xof": amendment.previous_amount_xof,
                    "total_xof": amendment.total_xof,
                }
            },
            fields={"amount_xof": amendment.total_xof},
        )  # fmt: skip
        audit(
            action="bookings.amendment.accepted",
            actor=actor,
            target=amendment,
            metadata={
                "previous_xof": amendment.previous_amount_xof,
                "total_xof": amendment.total_xof,
            },
        )
    else:
        audit(action="bookings.amendment.declined", actor=actor, target=amendment)
    _close_amendment(amendment, done)
    events.notify(events.AMENDMENT_DECIDED, [provider_owner], booking.public_id)
    return booking


@transaction.atomic
def accept_amendment(*, amendment: Amendment, actor: User) -> Booking:
    """Le client accepte (depuis sa session seulement) : ``amount_xof`` prend le total de
    l'avenant, via ``transition(in_progress → in_progress)``. Rejoué : 200."""
    return _decide_amendment(amendment=amendment, actor=actor, accept=True)


@transaction.atomic
def decline_amendment(*, amendment: Amendment, actor: User) -> Booking:
    """Le client refuse : le travail continue au prix courant. Rejoué : 200."""
    return _decide_amendment(amendment=amendment, actor=actor, accept=False)


# --- Photos (spec 004, ADR 0011) ------------------------------------------------------------------

# Statuts où l'envoi est ouvert : de la présence du pro à la contestation.
PHOTO_STATUSES = (Status.ON_SITE, Status.IN_PROGRESS, Status.COMPLETED, Status.DISPUTED)


@dataclass(frozen=True)
class UploadedPhoto:
    photo: BookingPhoto
    created: bool  # False : même clé et même fichier, la photo existante est rendue


def photo_keys(photo: BookingPhoto) -> tuple[str, str]:
    """Clés d'objet : des ``public_id`` seulement, jamais un nom, un numéro ni une date."""
    base = f"bookings/{photo.booking.public_id}/{photo.public_id}"
    return f"{base}.webp", f"{base}-thumb.webp"


def upload_photo(
    *,
    booking: Booking,
    actor: User,
    phase: str,
    content: bytes,
    idempotency_key: str,
    taken_at: datetime | None = None,
) -> UploadedPhoto:
    """Le gérant envoie une photo (de ``on_site`` à ``disputed``) : vérifiée par décodage,
    redressée, réduite à 1 600 px et réencodée en WebP **sans métadonnée**. L'original et son GPS
    ne sont jamais écrits. Idempotent par ``(réservation, Idempotency-Key)``.

    Refus : ``413 photo_too_large``, ``422 photo_invalid`` (image illisible, type ou taille
    décodée non permis, phase inconnue, ``taken_at`` dans le futur), ``409 photo_limit_reached``
    (5 par phase), ``409 idempotency_key_reused`` (autre fichier), ``409 transition_not_allowed``
    (hors de ``on_site`` à ``disputed``). Un pro suspendu n'envoie que pour une intervention
    ``in_progress`` (``403 provider_not_verified`` sinon).
    """
    from .tasks import make_thumbnail

    if not request_services.IDEMPOTENCY_KEY.match(idempotency_key or ""):
        raise DomainError("idempotency_key_required")
    if phase not in BookingPhoto.Phase.values:
        raise DomainError("photo_invalid", status=422)
    if len(content) > settings.BOOKING_PHOTO_MAX_BYTES:
        raise DomainError("photo_too_large", status=413)
    digest = hashlib.sha256(phase.encode() + b"\0" + content).hexdigest()
    written: list[str] = []
    try:
        with transaction.atomic():
            provider, _, locked = _lock_for_booking(booking)
            if provider.owner_id != actor.id:
                raise DomainError("not_found", status=404)
            replay = BookingPhoto.objects.filter(booking=locked, idempotency_key=idempotency_key)
            existing = replay.first()
            if existing is not None:
                if existing.source_hash != digest:
                    raise DomainError("idempotency_key_reused", status=409)
                return UploadedPhoto(existing, created=False)
            if locked.status not in PHOTO_STATUSES:
                raise DomainError("transition_not_allowed", status=409)
            if provider.status != Provider.Status.VERIFIED and locked.status != Status.IN_PROGRESS:
                raise DomainError("provider_not_verified", status=403)
            now = timezone.now()
            if taken_at is not None and taken_at > now + timedelta(minutes=5):
                raise DomainError("photo_invalid", status=422)
            taken = BookingPhoto.objects.filter(
                booking=locked, phase=phase, purged_at__isnull=True
            ).exclude(status=BookingPhoto.Status.FAILED)
            if taken.count() >= settings.BOOKING_PHOTO_MAX_PER_PHASE:
                raise DomainError("photo_limit_reached", status=409)
            try:
                image = reencode(
                    content,
                    max_edge=settings.BOOKING_PHOTO_MAX_EDGE,
                    quality=settings.BOOKING_PHOTO_QUALITY,
                )
            except InvalidImage:
                raise DomainError("photo_invalid", status=422) from None
            photo = BookingPhoto(
                booking=locked,
                phase=phase,
                width=image.width,
                height=image.height,
                size_bytes=image.size_bytes,
                taken_at=taken_at,
                idempotency_key=idempotency_key,
                source_hash=digest,
            )
            photo.image_key = photo_keys(photo)[0]
            storage.put(photo.image_key, image.content)
            written.append(photo.image_key)
            photo.save()
            audit(
                action="bookings.photo.uploaded",
                actor=actor,
                target=photo,
                metadata={"phase": phase},
            )
            public_id = str(photo.public_id)
            transaction.on_commit(lambda: make_thumbnail.delay(public_id))
            return UploadedPhoto(photo, created=True)
    except Exception:
        for key in written:  # rien ne reste dans le stockage si la base a refusé
            storage.delete(key)
        raise


def photo_urls(photo: BookingPhoto) -> dict:
    """URL signées (10 min) de la miniature et de l'image pleine, et leur échéance. Tant que la
    miniature n'existe pas, ``thumb_url`` est l'image pleine."""
    expires_at = timezone.now() + timedelta(seconds=settings.BOOKING_PHOTO_URL_TTL)
    full = storage.signed_url(photo.image_key)
    thumb = storage.signed_url(photo.thumb_key) if photo.thumb_key else full
    return {"thumb_url": thumb, "url": full, "expires_at": expires_at}


def make_thumbnail(*, photo_public_id: str) -> bool:
    """Produit la miniature (400 px, WebP) et passe la photo à ``ready``. Idempotente : une photo
    prête, purgée ou inconnue ne fait rien. Image absente du stockage : ``failed``."""
    photo = BookingPhoto.objects.select_related("booking").filter(public_id=photo_public_id).first()
    if photo is None or photo.purged_at or (photo.thumb_key and photo.status == "ready"):
        return False
    try:
        original = storage.read(photo.image_key)
    except FileNotFoundError:
        BookingPhoto.objects.filter(pk=photo.pk).update(status=BookingPhoto.Status.FAILED)
        return False
    thumb = reencode(
        original,
        max_edge=settings.BOOKING_PHOTO_THUMB_EDGE,
        quality=settings.BOOKING_PHOTO_THUMB_QUALITY,
    )
    thumb_key = photo_keys(photo)[1]
    storage.put(thumb_key, thumb.content)
    BookingPhoto.objects.filter(pk=photo.pk, purged_at__isnull=True).update(
        thumb_key=thumb_key, status=BookingPhoto.Status.READY
    )
    return True


@transaction.atomic
def report_photo(*, booking: Booking, photo_public_id, actor: User) -> BookingPhoto:
    """Le client signale une photo : elle est masquée pour lui et pour le pro, et gardée pour
    l'Ops (litige). Rejoué : l'état courant."""
    booking = Booking.objects.select_for_update().get(pk=booking.pk)
    if booking.client_id != actor.id:
        raise DomainError("not_found", status=404)
    photo = (
        BookingPhoto.objects.select_for_update()
        .filter(booking=booking, public_id=photo_public_id, purged_at__isnull=True)
        .first()
    )
    if photo is None:
        raise DomainError("not_found", status=404)
    if photo.hidden_at is None:
        photo.hidden_at = timezone.now()
        photo.hidden_by = actor
        photo.save(update_fields=["hidden_at", "hidden_by", "updated_at"])
        audit(
            action="bookings.photo.reported",
            actor=actor,
            target=photo,
            metadata={"phase": photo.phase},
        )
    return photo


def purge_booking_photos(photos) -> int:
    """Supprime les objets de ces photos (après le commit) et marque les lignes purgées.
    Renvoie le nombre de photos purgées. Les écritures sont atomiques, les suppressions d'objets
    partent après le commit de la transaction englobante."""
    from .tasks import delete_objects

    with transaction.atomic():
        rows = list(photos.select_for_update().filter(purged_at__isnull=True))
        if not rows:
            return 0
        keys = [key for row in rows for key in (row.image_key, row.thumb_key) if key]
        BookingPhoto.objects.filter(pk__in=[row.pk for row in rows]).update(
            purged_at=timezone.now(), image_key="", thumb_key=""
        )
        transaction.on_commit(lambda: delete_objects.delay(keys))
    return len(rows)


def purge_photos(*, now: datetime | None = None) -> int:
    """Rétention : les photos sont gardées 12 mois après la clôture, puis supprimées. Idempotent."""
    now = now or timezone.now()
    due = BookingPhoto.objects.filter(
        booking__status=Status.CLOSED,
        booking__closed_at__lte=now - settings.BOOKING_PHOTO_RETENTION,
        purged_at__isnull=True,
    )
    with transaction.atomic():
        count = purge_booking_photos(due)
        if count:
            audit(
                action="bookings.photos.purged",
                actor_kind=AuditEvent.ActorKind.SYSTEM,
                metadata={"count": count, "reason": "retention"},
            )
    return count


def purge_contact(*, now: datetime | None = None) -> int:
    """Repère et position des demandes dont la réservation est close depuis 90 jours : vidés."""
    now = now or timezone.now()
    cutoff = now - settings.BOOKING_CONTACT_RETENTION
    request_ids = list(
        Booking.objects.filter(status=Status.CLOSED, closed_at__lte=cutoff).values_list(
            "request_id", flat=True
        )
    )
    return request_services.clear_contact(request_ids)


def missing_photos(provider: Provider) -> dict[str, int]:
    """Drapeaux pour l'Ops : réservations closes d'un pro sans aucune photo « avant » ou
    « après » arrivée, malgré ``photos_pending``."""
    closed = Booking.objects.filter(provider=provider, status=Status.CLOSED)
    with_photos = BookingPhoto.objects.visible().filter(booking=OuterRef("pk"))
    return {
        "closed": closed.count(),
        "before_photos_missing": closed.filter(started_at__isnull=False)
        .exclude(Exists(with_photos.filter(phase="before")))
        .count(),
        "after_photos_missing": closed.filter(completed_at__isnull=False)
        .exclude(Exists(with_photos.filter(phase="after")))
        .count(),
    }


# --- Code de fin de mission (spec 004) -----------------------------------------------------------

CODE_STATUSES = (Status.SCHEDULED, Status.EN_ROUTE, Status.ON_SITE, Status.IN_PROGRESS)
NO_CODE_REASONS = ("client_absent", "client_no_phone", "code_locked", "client_refuses")
CLIENT_REFUSES = "client_refuses"
_PAST_COMPLETE = (Status.COMPLETED, Status.DISPUTED, Status.CLOSED)


def generate_completion_code() -> str:
    digits = settings.COMPLETION_CODE_DIGITS
    return str(secrets.randbelow(10**digits)).zfill(digits)


def visible_completion_code(booking: Booking) -> str | None:
    """Le code, pour le client seul, tant que la mission peut encore se terminer."""
    if booking.status not in CODE_STATUSES:
        return None
    return crypto.decrypt(booking.completion_code_enc)


def _send_code_sms(booking: Booking, *, automatic: bool) -> None:
    """Notification ``completion_code.sms`` : type et ``public_id`` seulement. Le futur adaptateur
    SMS rend le gabarit côté serveur ; le code ne passe jamais par ``notify()``."""
    if not booking.completion_code_enc:
        return
    booking.completion_code_sms_sent += 1
    booking.save(update_fields=["completion_code_sms_sent", "updated_at"])
    audit(
        action="bookings.completion_code.sms",
        actor=None if automatic else booking.client,
        actor_kind=AuditEvent.ActorKind.SYSTEM if automatic else AuditEvent.ActorKind.USER,
        target=booking,
        metadata={"automatic": automatic, "sent": booking.completion_code_sms_sent},
    )
    events.notify(events.COMPLETION_CODE_SMS, [booking.client], booking.public_id)


def _lock_for_client(booking: Booking, actor: User) -> Booking:
    _, _, booking = _lock_for_booking(booking)
    if booking.client_id != actor.id:
        raise DomainError("not_found", status=404)
    if booking.status not in CODE_STATUSES:
        raise DomainError("transition_not_allowed", status=409)
    return booking


@transaction.atomic
def regenerate_completion_code(*, booking: Booking, actor: User) -> Booking:
    """Le client obtient un nouveau code (3 fois au plus) : compteur d'essais remis à zéro, code
    débloqué. ``409 completion_code_regen_limit`` au-delà."""
    booking = _lock_for_client(booking, actor)
    if booking.completion_code_regenerations >= settings.COMPLETION_CODE_MAX_REGENERATIONS:
        raise DomainError("completion_code_regen_limit", status=409)
    booking.completion_code_enc = crypto.encrypt(generate_completion_code())
    booking.completion_code_attempts = 0
    booking.completion_code_locked = False
    booking.completion_code_regenerations += 1
    booking.save(
        update_fields=[
            "completion_code_enc",
            "completion_code_attempts",
            "completion_code_locked",
            "completion_code_regenerations",
            "updated_at",
        ]
    )
    audit(
        action="bookings.completion_code.regenerated",
        actor=actor,
        target=booking,
        metadata={"regenerations": booking.completion_code_regenerations},
    )
    return booking


@transaction.atomic
def send_completion_code_sms(*, booking: Booking, actor: User) -> Booking:
    """Le client demande un SMS de son code : 2 sur demande, en plus de l'envoi automatique du
    départ du pro. ``429 sms_limit_reached`` au-delà."""
    booking = _lock_for_client(booking, actor)
    limit = settings.COMPLETION_CODE_SMS_ON_DEMAND + (
        settings.COMPLETION_CODE_SMS_AUTO if booking.en_route_at else 0
    )
    if booking.completion_code_sms_sent >= limit:
        raise DomainError("sms_limit_reached", status=429)
    _send_code_sms(booking, automatic=False)
    return booking


def complete_work(
    *,
    booking: Booking,
    actor: User,
    code: str | None = None,
    no_code_reason: str | None = None,
    photos_pending: bool = False,
    occurred_at: datetime | None = None,
) -> Booking:
    """Le pro termine (``in_progress`` → ``completed``) avec le code du client, ou sans code et
    avec un motif (``NO_CODE_REASONS``). Un pro suspendu peut terminer une intervention en cours.

    - ``422 completion_proof_required`` : ni code ni motif, ou les deux ;
    - ``422 after_photos_required`` : ni photo « après » ni ``photos_pending`` (et, pour
      ``client_refuses``, une photo est obligatoire : ``photos_pending`` est refusé) ;
    - ``422 completion_code_invalid`` (l'essai est compté, 5 au plus) puis
      ``409 completion_code_locked`` ;
    - ``422 no_code_reason_invalid`` (``code_locked`` seulement si le code est verrouillé).

    Sans code, la fenêtre de contestation passe à 72 h. Rejouée une fois terminée : l'état courant.
    Le code n'est jamais écrit dans un log, un audit ni une erreur.
    """
    failure: DomainError | None = None
    with transaction.atomic():
        booking = _lock_for_pro(booking, actor, verified=False)
        if booking.status in _PAST_COMPLETE:
            return booking
        if booking.status != Status.IN_PROGRESS:
            raise DomainError("transition_not_allowed", status=409)
        code = code or None
        no_code_reason = no_code_reason or None
        if (code is None) == (no_code_reason is None):
            raise DomainError("completion_proof_required", status=422)
        if no_code_reason is not None and (
            no_code_reason not in NO_CODE_REASONS
            or (no_code_reason == "code_locked" and not booking.completion_code_locked)
        ):
            raise DomainError("no_code_reason_invalid", status=422)
        if not has_photos(booking, "after") and (
            no_code_reason == CLIENT_REFUSES or not photos_pending
        ):
            raise DomainError("after_photos_required", status=422)
        check_occurred_at(booking, occurred_at, now=timezone.now())
        if code is not None:
            if booking.completion_code_locked:
                raise DomainError("completion_code_locked", status=409)
            failure = _check_completion_code(booking, actor, code)
        if failure is None:
            _lapse_amendments(booking)
            method = (
                Booking.CompletionMethod.NO_CODE
                if no_code_reason
                else Booking.CompletionMethod.CODE
            )
            meta = {"completion_method": method} | _occurred(occurred_at)
            if photos_pending:
                meta["photos_pending"] = True
            booking = transition(
                booking, to=Status.COMPLETED, actor=actor, actor_kind=Actor.PRO, reason="completed",
                metadata=meta,
                fields={"completion_method": method, "no_code_reason": no_code_reason or ""},
            )  # fmt: skip
            audit(
                action="bookings.booking.completed",
                actor=actor,
                target=booking,
                metadata={"completion_method": method, "no_code_reason": no_code_reason or ""},
            )
            events.notify(events.BOOKING_COMPLETED, [booking.client], booking.public_id)
    if failure is not None:
        raise failure  # après le commit : l'essai compté reste
    return booking


def _check_completion_code(booking: Booking, actor: User, code: str) -> DomainError | None:
    """Compare en temps constant. Un code mal formé ne compte pas comme un essai (il ne peut pas
    être juste) ; un code faux le compte, et le 5e verrouille. Renvoie l'erreur à lever."""
    if not (code.isascii() and code.isdigit() and len(code) == settings.COMPLETION_CODE_DIGITS):
        return DomainError("completion_code_invalid", status=422)
    expected = crypto.decrypt(booking.completion_code_enc) or ""
    if expected and hmac.compare_digest(expected.encode(), code.encode()):
        return None
    booking.completion_code_attempts += 1
    booking.completion_code_locked = (
        booking.completion_code_attempts >= settings.COMPLETION_CODE_MAX_ATTEMPTS
    )
    booking.save(update_fields=["completion_code_attempts", "completion_code_locked", "updated_at"])
    audit(
        action="bookings.completion_code.failed",
        actor=actor,
        target=booking,
        metadata={
            "attempts": booking.completion_code_attempts,
            "locked": booking.completion_code_locked,
        },
    )
    return DomainError("completion_code_invalid", status=422)


# --- Litige (spec 004) : ouverture par le client, décision de l'Ops ------------------------------

DISPUTE_RELIABILITY_WEIGHT = 2  # un litige tranché en faveur du client, journalisé sur la clôture


@transaction.atomic
def open_dispute(*, booking: Booking, actor: User, reason: str, description: str) -> Booking:
    """Le client conteste (``completed`` → ``disputed``) avant ``dispute_deadline``, avec un motif
    et un texte de 10 à 1 000 caractères. Le litige (``trust.Dispute``) est créé dans la même
    transaction. Rejoué : l'état courant.

    ``409 dispute_window_closed`` après l'échéance ou la clôture ; ``409 transition_not_allowed``
    avant ``completed`` ; ``422 reason_invalid`` et ``description_invalid``.
    """
    provider, _, booking = _lock_for_booking(booking)
    if booking.client_id != actor.id:
        raise DomainError("not_found", status=404)
    if booking.status == Status.DISPUTED:
        return booking
    elapsed = booking.dispute_deadline is not None and timezone.now() > booking.dispute_deadline
    if booking.status == Status.CLOSED or (booking.status == Status.COMPLETED and elapsed):
        raise DomainError("dispute_window_closed", status=409)
    if booking.status != Status.COMPLETED:
        raise DomainError("transition_not_allowed", status=409)
    text = trust_services.clean_dispute_text(reason, description)
    booking = transition(
        booking, to=Status.DISPUTED, actor=actor, actor_kind=Actor.CLIENT, reason="dispute_opened"
    )
    trust_services.open_dispute(booking=booking, reason=reason, description=text)
    audit(
        action="bookings.booking.disputed", actor=actor, target=booking, metadata={"reason": reason}
    )
    events.notify(events.BOOKING_DISPUTED, [provider.owner], booking.public_id)
    return booking


@transaction.atomic
def resolve_dispute(*, dispute: Dispute, decision: str, note: str, operator: User) -> Booking:
    """L'Ops tranche : ``disputed`` → ``closed`` (acteur ``ops``, motif ``dispute_<décision>``),
    puis la décision est enregistrée par ``trust.services`` et auditée. Aucun remboursement en V1.

    ``for_client`` : le pro est averti, un poids de fiabilité de 2 est journalisé sur l'événement
    de clôture, et l'avis du client reste possible 7 jours après la décision. Les gestionnaires de
    clôture reçoivent le motif ``dispute_<décision>`` (l'étape 5 y lira la décision).
    """
    if decision not in Dispute.Decision.values:
        raise DomainError("decision_invalid", status=422)
    provider, _, booking = _lock_for_booking(dispute.booking)
    dispute = trust_services.lock_dispute(dispute)
    if dispute.status != Dispute.Status.OPEN or booking.status != Status.DISPUTED:
        raise DomainError("transition_not_allowed", status=409)
    weight = DISPUTE_RELIABILITY_WEIGHT if decision == Dispute.Decision.FOR_CLIENT else 0
    booking = transition(
        booking, to=Status.CLOSED, actor=operator, actor_kind=Actor.OPS,
        reason=f"dispute_{decision}",
        metadata={"dispute_decision": decision, "reliability_weight": weight},
    )  # fmt: skip
    trust_services.record_decision(dispute=dispute, decision=decision, note=note, operator=operator)
    audit(
        action="bookings.dispute.decided",
        actor=operator,
        actor_kind=AuditEvent.ActorKind.OPS,
        target=booking,
        metadata={"decision": decision, "reliability_weight": weight},
    )
    events.notify(events.DISPUTE_DECIDED, [provider.owner, booking.client], booking.public_id)
    return booking


def dispute_photo_links(*, dispute: Dispute, operator: User) -> list[dict]:
    """Photos du litige pour l'Ops, signalées comprises (le client a pu en masquer), en URL
    signées de 10 min. Chaque consultation est auditée ; seul un litige donne accès aux photos."""
    photos = list(
        BookingPhoto.objects.filter(booking=dispute.booking, purged_at__isnull=True)
        .exclude(status=BookingPhoto.Status.FAILED)
        .order_by("created_at", "id")
    )
    audit(
        action="bookings.photos.viewed",
        actor=operator,
        actor_kind=AuditEvent.ActorKind.OPS,
        target=dispute,
        metadata={"count": len(photos)},
    )
    return [{"phase": p.phase, "hidden": p.hidden_at is not None, **photo_urls(p)} for p in photos]


@transaction.atomic
def restore_photo(*, photo: BookingPhoto, operator: User) -> BookingPhoto:
    """L'Ops réaffiche une photo signalée, seulement si la réservation a un litige. Audité."""
    photo = BookingPhoto.objects.select_for_update().get(pk=photo.pk)
    if photo.purged_at is not None or not Dispute.objects.filter(booking=photo.booking).exists():
        raise DomainError("photo_restore_refused", status=409)
    if photo.hidden_at is not None:
        photo.hidden_at = None
        photo.hidden_by = None
        photo.save(update_fields=["hidden_at", "hidden_by", "updated_at"])
        audit(
            action="bookings.photo.restored",
            actor=operator,
            actor_kind=AuditEvent.ActorKind.OPS,
            target=photo,
            metadata={"phase": photo.phase},
        )
    return photo


# --- No-show : « le pro n'est pas venu » (spec 004) ----------------------------------------------


def no_show_available_at(booking: Booking) -> datetime:
    """Heure à partir de laquelle le client peut déclarer un no-show : fin du créneau + marge."""
    return booking.slot_end + settings.BOOKING_NO_SHOW_GRACE


def can_report_no_show(booking: Booking, *, now: datetime | None = None) -> bool:
    return booking.status in {Status.SCHEDULED, Status.EN_ROUTE} and (
        (now or timezone.now()) >= no_show_available_at(booking)
    )


def _is_no_show(booking: Booking) -> bool:
    return booking.status == Status.CANCELLED and booking.cancel_reason == PRO_NO_SHOW


@transaction.atomic
def declare_no_show(*, booking: Booking, actor: User) -> Booking:
    """Le client déclare que le pro n'est pas venu : ``scheduled`` ou ``en_route`` à ``cancelled``
    (acteur client, motif ``pro_no_show``), avec les effets d'un désistement du pro.

    Possible à partir de ``slot_end`` + ``BOOKING_NO_SHOW_GRACE`` (``409 no_show_too_early``).
    Rejoué : l'état courant. Le poids de fiabilité attend la confirmation (``NoShowReport``).
    """
    provider, request, booking = _lock_for_booking(booking)
    if booking.client_id != actor.id:
        raise DomainError("not_found", status=404)
    if _is_no_show(booking) and booking.cancelled_by == Actor.CLIENT:
        return booking
    if booking.status not in {Status.SCHEDULED, Status.EN_ROUTE}:
        raise DomainError("transition_not_allowed", status=409)
    if not can_report_no_show(booking):
        raise DomainError("no_show_too_early", status=409)
    booking = _cancel(
        booking, request, provider, actor=actor, actor_kind=Actor.CLIENT, reason=PRO_NO_SHOW
    )
    NoShowReport.objects.create(booking=booking)
    return booking


def contest_deadline(report: NoShowReport) -> datetime:
    return report.created_at + settings.BOOKING_NO_SHOW_CONTEST_WINDOW


@transaction.atomic
def contest_no_show(*, booking: Booking, actor: User, note: str) -> Booking:
    """Le pro conteste, en un geste et avec une note (numéros refusés), dans les 24 h.

    ``409 no_show_contest_closed`` après la fenêtre ou une décision ; ``422 note_invalid``. Un
    pro suspendu peut contester. Rejoué : l'état courant. La note n'est jamais journalisée.
    """
    booking = _lock_for_pro(booking, actor, verified=False)
    report = NoShowReport.objects.select_for_update().filter(booking=booking).first()
    if report is None:
        raise DomainError("transition_not_allowed", status=409)
    if report.status == NoShowReport.Status.CONTESTED:
        return booking
    if report.status != NoShowReport.Status.PENDING or timezone.now() > contest_deadline(report):
        raise DomainError("no_show_contest_closed", status=409)
    clean = clean_note(note)
    if not clean:
        raise DomainError("note_invalid", status=422)
    report.status = NoShowReport.Status.CONTESTED
    report.contest_note = clean
    report.contested_at = timezone.now()
    report.save(update_fields=["status", "contest_note", "contested_at", "updated_at"])
    audit(action="bookings.no_show.contested", actor=actor, target=booking)
    events.notify(events.NO_SHOW_CONTESTED, [booking.client], booking.public_id)
    return booking


def _decide(report: NoShowReport, *, to: str, operator: User | None) -> None:
    weight = NO_SHOW_WEIGHT if to == NoShowReport.Status.CONFIRMED else 0
    report.status = to
    report.decided_by = operator
    report.decided_at = timezone.now()
    report.save(update_fields=["status", "decided_by", "decided_at", "updated_at"])
    audit(
        action="bookings.no_show.decided",
        actor=operator,
        actor_kind=AuditEvent.ActorKind.OPS if operator else AuditEvent.ActorKind.SYSTEM,
        target=report,
        metadata={"decision": to, "reliability_weight": weight},
    )


def confirm_no_shows(*, now: datetime | None = None) -> int:
    """Confirme les no-shows sans contestation après 24 h : c'est là que le poids 3 s'applique.
    Idempotent."""
    now = now or timezone.now()
    cutoff = now - settings.BOOKING_NO_SHOW_CONTEST_WINDOW
    due = NoShowReport.objects.filter(status=NoShowReport.Status.PENDING, created_at__lte=cutoff)
    confirmed = 0
    for pk in list(due.values_list("pk", flat=True)):
        with transaction.atomic():
            report = NoShowReport.objects.select_for_update().get(pk=pk)
            if report.status != NoShowReport.Status.PENDING:
                continue  # contesté entre-temps
            _decide(report, to=NoShowReport.Status.CONFIRMED, operator=None)
            confirmed += 1
    return confirmed


@transaction.atomic
def decide_no_show(*, report: NoShowReport, decision: str, operator: User) -> NoShowReport:
    """L'Ops confirme ou écarte un no-show (en attente ou contesté). Journalisé."""
    if decision not in {NoShowReport.Status.CONFIRMED, NoShowReport.Status.DISMISSED}:
        raise DomainError("decision_invalid", status=422)
    report = NoShowReport.objects.select_for_update().get(pk=report.pk)
    if report.status not in {NoShowReport.Status.PENDING, NoShowReport.Status.CONTESTED}:
        raise DomainError("transition_not_allowed", status=409)
    _decide(report, to=decision, operator=operator)
    return report


def no_show_check(*, now: datetime | None = None) -> int:
    """Interroge le client, une seule fois, quand le pro n'a rien saisi après le créneau.

    Aucune annulation automatique : le pro est peut-être venu sans rien saisir.
    """
    now = now or timezone.now()
    due = Booking.objects.filter(
        status__in=(Status.SCHEDULED, Status.EN_ROUTE),
        no_show_check_sent_at__isnull=True,
        slot_end__lte=now - settings.BOOKING_NO_SHOW_GRACE,
    )
    sent = 0
    for pk in list(due.values_list("pk", flat=True)):
        with transaction.atomic():
            locked = Booking.objects.select_for_update().select_related("client").get(pk=pk)
            if locked.status not in {Status.SCHEDULED, Status.EN_ROUTE}:
                continue
            if locked.no_show_check_sent_at:
                continue
            locked.no_show_check_sent_at = now
            locked.save(update_fields=["no_show_check_sent_at", "updated_at"])
            events.notify(events.NO_SHOW_CHECK, [locked.client], locked.public_id)
            sent += 1
    return sent


# --- Annulations ------------------------------------------------------------------------------


def _cancel(
    booking: Booking,
    request: ServiceRequest,
    provider: Provider,
    *,
    actor: User | None,
    actor_kind: str,
    reason: str,
    note: str = "",
) -> Booking:
    """Annule (objets déjà verrouillés) et applique les effets sur la demande et les devis."""
    previous = booking.status
    booking = transition(
        booking, to=Status.CANCELLED, actor=actor, actor_kind=actor_kind, reason=reason, note=note
    )
    event = booking.events.order_by("-id").first()
    # La partie fautive décide des effets : un no-show déclaré par le client est un désistement
    # du pro (demande rouverte, pro exclu), pas une annulation du client.
    if actor_kind == Actor.CLIENT and reason != PRO_NO_SHOW:
        request_services.release_after_client_cancel(request=request, reason=reason)
    else:
        quote_services.release_after_pro_cancel(
            request=request, quote=booking.quote, provider=provider, now=timezone.now()
        )
    audit(
        action="bookings.booking.cancelled",
        actor=actor,
        actor_kind=_audit_kind(actor_kind),
        target=booking,
        metadata={
            "from_status": previous,
            "cancelled_by": actor_kind,
            "reason": reason,
            "late": bool(event.metadata.get("late")),
            "reliability_weight": int(event.metadata.get("reliability_weight", 0)),
        },
    )
    # L'autre partie est prévenue (les deux si c'est le système) : le client reçoit un message
    # neutre quand le pro se désiste.
    recipients = {
        Actor.CLIENT: [provider.owner],
        Actor.PRO: [booking.client],
    }.get(actor_kind, [booking.client, provider.owner])
    events.notify(events.BOOKING_CANCELLED, recipients, booking.public_id)
    return booking


def _audit_kind(actor_kind: str) -> str:
    return AuditEvent.ActorKind.SYSTEM if actor_kind == Actor.SYSTEM else AuditEvent.ActorKind.USER


def cancel_booking(
    *, booking: Booking, actor: User, actor_kind: str, reason: str, note: str | None = None
) -> Booking:
    """Le client ou le pro annule une réservation de ``accepted`` à ``on_site``, avec un motif.

    Le client ne peut plus annuler un pro déjà sur place (``409 transition_not_allowed``). Le
    motif ``client_absent`` n'existe que pour le pro sur place. Le pro suspendu n'écrit plus.
    Le client reçoit un message neutre si le pro se désiste.
    """
    if actor_kind not in {Actor.CLIENT, Actor.PRO}:
        raise DomainError("transition_not_allowed", status=409)
    allowed = CLIENT_REASONS if actor_kind == Actor.CLIENT else PRO_REASONS
    clean_note = check_reason(reason, allowed=allowed, note=note)
    with transaction.atomic():
        provider, request, booking = _lock_for_booking(booking)
        owner_id = booking.client_id if actor_kind == Actor.CLIENT else provider.owner_id
        if owner_id != actor.id:
            raise DomainError("not_found", status=404)
        if actor_kind == Actor.PRO and provider.status != Provider.Status.VERIFIED:
            raise DomainError("provider_not_verified", status=403)
        if reason == CLIENT_ABSENT and booking.status != Status.ON_SITE:
            raise DomainError("reason_invalid", status=422)  # le pro doit être sur place
        return _cancel(
            booking, request, provider, actor=actor, actor_kind=actor_kind, reason=reason,
            note=clean_note,
        )  # fmt: skip


def cancel_unconfirmed(*, now: datetime | None = None) -> int:
    """Annule les réservations ``accepted`` dont le pro n'a pas confirmé à temps (système,
    ``pro_unconfirmed``, poids 0). Idempotent. Renvoie le nombre annulé."""
    now = now or timezone.now()
    due = Booking.objects.filter(status=Status.ACCEPTED, confirm_deadline__lte=now)
    cancelled = 0
    for booking in list(due.select_related("provider")):
        with transaction.atomic():
            provider, request, locked = _lock_for_booking(booking)
            # Relue sous verrou : le pro a pu confirmer, le client annuler.
            if locked.status != Status.ACCEPTED or locked.confirm_deadline > now:
                continue
            _cancel(locked, request, provider, actor=None, actor_kind=Actor.SYSTEM,
                    reason="pro_unconfirmed")  # fmt: skip
            cancelled += 1
    return cancelled


def cancel_for_suspended_provider(provider: Provider) -> int:
    """Suspension d'un pro : ses réservations, jusqu'à ``on_site``, sont annulées (système,
    ``provider_suspended``). Une intervention ``in_progress`` continue : le gérant suspendu peut
    encore la terminer (photos, code). Appelée dans la transaction de ``providers.set_status``."""
    cancelled = 0
    active = Booking.objects.filter(provider=provider, status__in=Booking.CANCELLABLE).order_by(
        "request_id"
    )  # verrous dans l'ordre croissant
    for booking in list(active):
        _, request, locked = _lock_for_booking(booking)
        if locked.status not in Booking.CANCELLABLE:
            continue
        _cancel(locked, request, provider, actor=None, actor_kind=Actor.SYSTEM,
                reason="provider_suspended")  # fmt: skip
        cancelled += 1
    return cancelled


# --- Données personnelles ---------------------------------------------------------------------


def deletion_blocker(user: User) -> str | None:
    """Un compte avec une réservation engagée (de ``accepted`` à ``disputed``, client ou pro) ne
    peut pas être supprimé. ``create_from_quote`` crée la réservation sous le verrou des deux
    comptes."""
    engaged = Booking.objects.filter(status__in=Booking.ENGAGED).filter(
        Q(client=user) | Q(provider__owner=user)
    )
    return "deletion_blocked_active_booking" if engaged.exists() else None


def anonymize_bookings(user: User) -> None:
    """Anonymiseur : les notes libres des événements et des contestations sont effacées."""
    BookingEvent.objects.filter(
        Q(actor=user) | Q(booking__client=user) | Q(booking__provider__owner=user)
    ).wipe_notes()
    # Photos du logement : objets supprimés après le commit (client ou gérant).
    purge_booking_photos(
        BookingPhoto.objects.filter(Q(booking__client=user) | Q(booking__provider__owner=user))
    )
    # Note d'avenant et libellés de ses lignes : textes libres du pro.
    Amendment.objects.filter(booking__provider__owner=user).update(note="")
    AmendmentLine.objects.filter(amendment__booking__provider__owner=user).update(label="")
    # La note de contestation d'un no-show est un texte libre du pro.
    NoShowReport.objects.filter(booking__provider__owner=user).update(contest_note="")
