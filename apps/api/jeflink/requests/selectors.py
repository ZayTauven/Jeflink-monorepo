"""Lectures de la demande (spec 003). Toute liste prend ``user`` ou ``provider`` : un objet
d'un autre utilisateur répond 404, jamais 403."""

from datetime import datetime

from django.db.models import QuerySet
from django.utils import timezone

from jeflink.accounts.models import User
from jeflink.common.errors import DomainError
from jeflink.providers.models import Provider

from .models import ServiceRequest


def requests_for_client(*, user: User) -> QuerySet[ServiceRequest]:
    return ServiceRequest.objects.filter(client=user).select_related("trade", "service", "zone")


def request_for_client(*, user: User, public_id) -> ServiceRequest:
    request = requests_for_client(user=user).filter(public_id=public_id).first()
    if request is None:
        raise DomainError("not_found", status=404)
    return request


def effective_status(request: ServiceRequest, *, now: datetime | None = None) -> str:
    """Statut affiché : une demande échue reste « expirée » même si la tâche a du retard."""
    now = now or timezone.now()
    live = {ServiceRequest.Status.OPEN, ServiceRequest.Status.QUOTED}
    if request.status in live and request.expires_at is not None and request.expires_at <= now:
        return ServiceRequest.Status.EXPIRED
    return request.status


def eligible_providers(request: ServiceRequest) -> QuerySet[Provider]:
    """Pros vérifiés qui peuvent voir la demande : son métier, sa zone, pas son propre client.

    Un pro qui s'est désisté de cette demande n'en fait plus partie. La demande d'un compte de
    revue des stores n'est visible que des pros de démo (spec 001, S17).
    """
    if request.zone_id is None:
        return Provider.objects.none()
    providers = (
        Provider.objects.filter(
            status=Provider.Status.VERIFIED, trades=request.trade_id, zones=request.zone_id
        )
        .exclude(owner_id=request.client_id)
        .exclude(excluded_requests=request)
    )
    if request.client.is_review_account:
        providers = providers.filter(is_demo=True)
    return providers.distinct()
