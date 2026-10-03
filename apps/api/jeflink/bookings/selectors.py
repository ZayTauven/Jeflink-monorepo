"""Lectures des réservations (spec 003). Toute liste prend ``user`` ou ``provider`` : la
réservation d'un autre répond 404. Une réservation ``accepted`` dont l'échéance de confirmation
est passée n'est plus montrée : un retard de la tâche d'annulation ne la fait pas revivre."""

from datetime import datetime

from django.db.models import Prefetch, Q, QuerySet
from django.utils import timezone

from jeflink.accounts.models import User
from jeflink.common.errors import DomainError
from jeflink.providers.models import Provider
from jeflink.requests.models import ServiceRequest

from .models import Amendment, Booking, BookingPhoto


def _photos() -> Prefetch:
    """Photos visibles, préchargées : une requête pour toutes les réservations de la page."""
    return Prefetch(
        "photos",
        queryset=BookingPhoto.objects.visible().order_by("created_at", "id"),
        to_attr="visible_photos",
    )


def _alive(now: datetime) -> Q:
    return ~Q(status=Booking.Status.ACCEPTED, confirm_deadline__lte=now)


def bookings_for_client(*, user: User, now: datetime | None = None) -> QuerySet[Booking]:
    return (
        Booking.objects.filter(_alive(now or timezone.now()), client=user)
        .select_related(
            "provider", "request__trade", "request__zone", "quote", "no_show", "dispute"
        )
        .prefetch_related("quote__lines", _photos(), "amendments__lines")
    )


def booking_for_client(*, user: User, public_id, now: datetime | None = None) -> Booking:
    booking = bookings_for_client(user=user, now=now).filter(public_id=public_id).first()
    if booking is None:
        raise DomainError("not_found", status=404)
    return booking


def bookings_for_provider(*, provider: Provider, now: datetime | None = None) -> QuerySet[Booking]:
    """Les réservations d'une fiche, suspendue comprise : elle lit encore, sans écrire."""
    return (
        Booking.objects.filter(_alive(now or timezone.now()), provider=provider)
        .select_related("client", "request__trade", "request__zone", "quote", "no_show", "dispute")
        .prefetch_related("quote__lines", _photos(), "amendments__lines")
    )


def booking_for_provider(*, provider: Provider, public_id, now: datetime | None = None) -> Booking:
    booking = bookings_for_provider(provider=provider, now=now).filter(public_id=public_id).first()
    if booking is None:
        raise DomainError("not_found", status=404)
    return booking


def withdrawn_by_provider(request: ServiceRequest, *, active: Booking | None) -> bool:
    """Le pro (ou le système) s'est désisté et la demande est revenue à ``open`` ou ``quoted``.

    Une requête au plus, et seulement si la demande est revenue sans réservation active. Aucun
    motif, aucun nom : le client lit « Le pro ne peut plus venir, voici vos autres devis ».
    """
    if active is not None or request.status not in {
        ServiceRequest.Status.OPEN,
        ServiceRequest.Status.QUOTED,
    }:
        return False
    last = Booking.objects.filter(request=request).order_by("-created_at", "-id").first()
    return last is not None and last.cancelled_by in {Booking.Actor.PRO, Booking.Actor.SYSTEM}


def active_booking_for_request(
    request: ServiceRequest, *, now: datetime | None = None
) -> Booking | None:
    """La réservation active de la demande (une seule, ADR 0010), s'il y en a une."""
    return (
        Booking.objects.filter(_alive(now or timezone.now()), request=request)
        .exclude(status=Booking.Status.CANCELLED)
        .select_related("provider", "quote")
        .prefetch_related("quote__lines", _photos(), "amendments__lines")
        .first()
    )


def amendment_for_provider(*, provider: Provider, public_id) -> Amendment:
    """L'avenant d'une réservation de ce pro ; celui d'un autre répond 404."""
    amendment = (
        Amendment.objects.filter(public_id=public_id, booking__provider=provider)
        .select_related("booking")
        .first()
    )
    if amendment is None:
        raise DomainError("not_found", status=404)
    return amendment


def amendment_for_client(*, user: User, booking_public_id, public_id) -> Amendment:
    amendment = (
        Amendment.objects.filter(
            public_id=public_id, booking__public_id=booking_public_id, booking__client=user
        )
        .select_related("booking")
        .first()
    )
    if amendment is None:
        raise DomainError("not_found", status=404)
    return amendment
