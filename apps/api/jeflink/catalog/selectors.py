"""Lectures du catalogue (spec 002).

``active_trades()`` est la liste que l'IA1 recevra (spec 003).
"""

from django.db.models import Prefetch, QuerySet

from jeflink.common.errors import DomainError
from jeflink.common.search import match

from .models import Service, Trade


def _active_services() -> Prefetch:
    return Prefetch("services", queryset=Service.objects.filter(is_active=True))


def active_trades() -> QuerySet[Trade]:
    """Métiers actifs et leurs services actifs, en deux requêtes, par ``position``."""
    return Trade.objects.filter(is_active=True).prefetch_related(_active_services())


def active_trade(slug: str) -> Trade:
    """Détail d'un métier actif ; un métier inconnu ou désactivé répond ``trade_not_found``."""
    trade = active_trades().filter(slug=slug).first()
    if trade is None:
        raise DomainError("trade_not_found", status=404)
    return trade


def trade_by_slug(slug: str) -> Trade | None:
    """Métier par son slug, actif ou non (données de référence des autres domaines)."""
    return Trade.objects.filter(slug=slug).first()


def trade_terms(trade: Trade) -> list[str]:
    return [trade.name_fr, trade.name_wo, trade.seo_title_fr, trade.slug, *trade.aliases]


def resolve_trade_text(text: str) -> list[Trade]:
    """Métiers actifs qui répondent aux mots du client (« frigoriste »), du plus proche au moins.

    Un alias partagé (« frigo ») renvoie plusieurs métiers : le client choisit.
    """
    ranked = [
        (rank, trade.position, trade.name_fr, trade)
        for trade in active_trades()
        if (rank := match(text, trade_terms(trade))) is not None
    ]
    return [item[-1] for item in sorted(ranked, key=lambda item: item[:3])]
