"""Écritures des réservations (spec 003 et 004, ADR 0010). Seul ce module écrit
``Booking.status`` (et, à partir des avenants, ``Booking.amount_xof``).

Ordre des verrous, partout : comptes (par id), fiche pro, demande, réservation. La note d'un
motif « autre » n'est jamais écrite dans un log ni dans un audit.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone

from jeflink.accounts.models import User
from jeflink.common.errors import DomainError
from jeflink.notifications import events
from jeflink.providers.models import Provider
from jeflink.requests import quotes as quote_services
from jeflink.requests import services as request_services
from jeflink.requests.models import Quote, ServiceRequest
from jeflink.requests.reasons import CLIENT_REASONS, PRO_REASONS, check_reason
from jeflink.trust.models import AuditEvent
from jeflink.trust.services import audit

from .machine import (
    ALWAYS_LATE_FROM,
    CLIENT_ABSENT,
    DECLARED,
    Actor,
    Status,
    confirm_deadline,
    is_late,
    reliability_weight,
)
from .models import Booking, BookingEvent

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
TRANSITION_FIELDS = frozenset({"amount_xof"})
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
    if previous == Status.ON_SITE and to == Status.IN_PROGRESS:
        booking.started_at = now
        update.append("started_at")
    if to == Status.COMPLETED:
        booking.dispute_deadline = now + settings.BOOKING_DISPUTE_WINDOW
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
    """Une photo de la phase est-elle arrivée ? (branché sur ``BookingPhoto`` à la tâche 5)."""
    return False


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
    if actor_kind == Actor.CLIENT:
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
    """Anonymiseur : les notes libres des événements de ses réservations sont effacées."""
    BookingEvent.objects.filter(
        Q(actor=user) | Q(booking__client=user) | Q(booking__provider__owner=user)
    ).wipe_notes()
