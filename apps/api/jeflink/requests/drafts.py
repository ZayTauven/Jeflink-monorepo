"""``RequestDraft`` : le contrat d'entrée de la demande (spec 003).

L'IA1 produira un brouillon à partir de ``catalog.selectors.active_trades()``, le client le
validera, puis il passera par le même ``create_request``.
"""

from dataclasses import dataclass
from datetime import date

from django.contrib.gis.geos import Point


@dataclass(frozen=True)
class RequestDraft:
    trade_slug: str
    service_slug: str | None = None
    # La zone vient de zone_slug, sinon de zone_text, sinon de location.
    zone_slug: str | None = None
    zone_text: str | None = None
    location: Point | None = None
    landmark: str = ""
    description: str = ""
    urgent: bool | None = None  # None : celui du service choisi
    preferred_when: str = "asap"
    preferred_date: date | None = None
    preferred_period: str = "any"
