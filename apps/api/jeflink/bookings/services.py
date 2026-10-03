"""Écritures des réservations (spec 003, ADR 0010). Seul ce module écrit ``Booking.status``.

Ordre des verrous, partout : comptes (par id), fiche pro, demande, réservation. La note d'un
motif « autre » n'est jamais écrite dans un log ni dans un audit.
"""

from dataclasses import dataclass
from datetime import datetime

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

from .machine import DECLARED, Actor, Status, confirm_deadline, is_late, reliability_weight
from .models import Booking, BookingEvent

# Clés permises dans ``BookingEvent.metadata`` (schéma fermé).
EVENT_METADATA_KEYS = frozenset({"late", "reliability_weight"})


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
) -> Booking:
    """Seul point de changement du statut d'une réservation.

    Verrouille la ligne, vérifie le couple (``transition_not_allowed`` s'il est interdit,
    ``transition_not_enabled`` s'il est déclaré mais pas encore activé) et l'acteur, écrit le
    statut puis un ``BookingEvent``. À appeler dans une transaction.
    """
    booking = Booking.objects.select_for_update().get(pk=booking.pk)
    rule = DECLARED.get((booking.status, to))
    if rule is None or actor_kind not in rule.actors:
        raise DomainError("transition_not_allowed", status=409)
    if not rule.enabled:
        raise DomainError("transition_not_enabled", status=409)
    now = timezone.now()
    metadata: dict = {}
    previous = booking.status
    if to == Status.CANCELLED:
        late = is_late(slot_start=booking.slot_start, now=now) and previous == Status.SCHEDULED
        metadata = {
            "late": late,
            "reliability_weight": reliability_weight(
                actor_kind=actor_kind, from_status=previous, to_status=to, late=late
            ),
        }
        booking.cancelled_by = actor_kind
        booking.cancel_reason = reason[:24]
    booking.status = to
    booking.save(update_fields=["status", "cancelled_by", "cancel_reason", "updated_at"])
    _write_event(
        booking,
        from_status=previous,
        to=to,
        actor=actor,
        actor_kind=actor_kind,
        reason=reason,
        note=note,
        metadata=metadata,
    )
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
    """Le client ou le pro annule une réservation ``accepted`` ou ``scheduled``, avec un motif.

    Le pro suspendu n'écrit plus. Le client reçoit un message neutre si le pro se désiste.
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
    """Suspension d'un pro : ses réservations actives sont annulées (système,
    ``provider_suspended``). Appelée dans la transaction de ``providers.set_status``."""
    cancelled = 0
    active = Booking.objects.filter(provider=provider, status__in=Booking.ACTIVE).order_by(
        "request_id"
    )  # verrous dans l'ordre croissant
    for booking in list(active):
        _, request, locked = _lock_for_booking(booking)
        if locked.status not in Booking.ACTIVE:
            continue
        _cancel(locked, request, provider, actor=None, actor_kind=Actor.SYSTEM,
                reason="provider_suspended")  # fmt: skip
        cancelled += 1
    return cancelled


# --- Données personnelles ---------------------------------------------------------------------


def deletion_blocker(user: User) -> str | None:
    """Un compte avec une réservation ``accepted`` ou ``scheduled`` (client ou pro) ne peut pas
    être supprimé. ``create_from_quote`` crée la réservation sous le verrou des deux comptes."""
    engaged = Booking.objects.filter(status__in=Booking.ACTIVE).filter(
        Q(client=user) | Q(provider__owner=user)
    )
    return "deletion_blocked_active_booking" if engaged.exists() else None


def anonymize_bookings(user: User) -> None:
    """Anonymiseur : les notes libres des événements de ses réservations sont effacées."""
    BookingEvent.objects.filter(
        Q(actor=user) | Q(booking__client=user) | Q(booking__provider__owner=user)
    ).wipe_notes()
