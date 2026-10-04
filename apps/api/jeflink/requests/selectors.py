"""Lectures de la demande (spec 003). Toute liste prend ``user`` ou ``provider`` : un objet
d'un autre utilisateur répond 404, jamais 403."""

from datetime import datetime

from django.conf import settings
from django.db.models import Count, Exists, OuterRef, Q, QuerySet
from django.utils import timezone

from jeflink.accounts.models import User
from jeflink.common.errors import DomainError
from jeflink.providers.models import Provider

from .models import Quote, ServiceRequest


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


# --- Diffusion aux pros et devis --------------------------------------------------------------


def _visible_to_provider(provider: Provider, now: datetime) -> QuerySet[ServiceRequest]:
    """Demandes que ce pro peut voir : vivantes, de son métier et de sa zone, jamais la
    sienne, jamais une demande dont il s'est désisté. Le temps courant filtre aussi : un retard
    de la tâche d'expiration ne montre jamais une demande échue."""
    if provider.status != Provider.Status.VERIFIED:
        return ServiceRequest.objects.none()
    requests = (
        ServiceRequest.objects.filter(
            status__in=(ServiceRequest.Status.OPEN, ServiceRequest.Status.QUOTED),
            expires_at__gt=now,
            trade__in=provider.trades.all(),
            zone__in=provider.zones.all(),
        )
        .exclude(client_id=provider.owner_id)
        .exclude(excluded_providers=provider)
        .select_related("trade", "service", "zone")
    )
    if not provider.is_demo:
        # Le compte de revue des stores n'est visible que des pros de démo (S17).
        requests = requests.filter(client__is_review_account=False)
    return requests


def requests_for_provider(*, provider: Provider, now: datetime | None = None):
    """« Demandes pour moi » : encore une place, et pas de devis actif de ce pro. Triées par
    urgence puis ancienneté (``dispatch_rank``)."""
    now = now or timezone.now()
    mine = Quote.objects.filter(request=OuterRef("pk"), provider=provider, status__in=Quote.ACTIVE)
    return (
        _visible_to_provider(provider, now)
        .annotate(
            active_quotes=Count("quotes", filter=Q(quotes__status__in=Quote.ACTIVE)),
            has_mine=Exists(mine),
        )
        .filter(active_quotes__lt=settings.QUOTE_MAX_ACTIVE, has_mine=False)
        .order_by("dispatch_rank", "id")
    )


def request_for_provider(*, provider: Provider, public_id, now: datetime | None = None):
    """Une demande visible du pro, même pleine ou déjà devisée par lui : l'envoi répond alors
    ``quotes_full`` ou ``quote_already_sent`` (409) plutôt qu'un 404."""
    now = now or timezone.now()
    request = (
        _visible_to_provider(provider, now)
        .annotate(active_quotes=Count("quotes", filter=Q(quotes__status__in=Quote.ACTIVE)))
        .filter(public_id=public_id)
        .first()
    )
    if request is None:
        raise DomainError("not_found", status=404)
    return request


def places_left(request: ServiceRequest) -> int:
    used = Quote.objects.filter(request=request, status__in=Quote.ACTIVE).count()
    return max(0, settings.QUOTE_MAX_ACTIVE - used)


def quotes_for_client_request(request: ServiceRequest, *, now: datetime | None = None):
    """Devis montrés au client : en lice (``submitted``, ``held``) ou accepté, triés par créneau
    le plus proche, **jamais par prix** (pas de course au moins-disant)."""
    now = now or timezone.now()
    return (
        Quote.objects.filter(request=request)
        .filter(
            Q(status=Quote.Status.SUBMITTED, valid_until__gt=now)
            | Q(status__in=(Quote.Status.HELD, Quote.Status.ACCEPTED))
        )
        .select_related("provider")
        .prefetch_related("lines")
        .order_by("slot_start", "id")
    )


def quotes_for_provider(*, provider: Provider) -> QuerySet[Quote]:
    return (
        Quote.objects.filter(provider=provider)
        .select_related("request__trade", "request__zone")
        .prefetch_related("lines")
    )


def quote_for_provider(*, provider: Provider, public_id) -> Quote:
    quote = quotes_for_provider(provider=provider).filter(public_id=public_id).first()
    if quote is None:
        raise DomainError("not_found", status=404)
    return quote


def quote_for_client(*, user: User, public_id) -> Quote:
    """Un devis sur une demande du client ; celui d'un autre client est un 404."""
    quote = (
        Quote.objects.filter(public_id=public_id, request__client=user)
        .select_related("request", "provider")
        .first()
    )
    if quote is None:
        raise DomainError("not_found", status=404)
    return quote
