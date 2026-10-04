"""Heure de Dakar : dates stockées en UTC, jours et plages lus en ``Africa/Dakar`` (règle 5)."""

from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from django.conf import settings

DAKAR = ZoneInfo("Africa/Dakar")


def dakar_now(now: datetime) -> datetime:
    return now.astimezone(DAKAR)


def dakar_today(now: datetime) -> date:
    return dakar_now(now).date()


def period_bounds(day: date, period: str) -> tuple[datetime, datetime]:
    """Début et fin (UTC) d'une plage (``morning``, ``afternoon``, ``evening``) un jour donné.

    Les heures de chaque plage sont un réglage (``SLOT_PERIODS``). ``KeyError`` si la plage est
    inconnue.
    """
    start_hour, end_hour = settings.SLOT_PERIODS[period]
    start = datetime.combine(day, time(start_hour), tzinfo=DAKAR)
    end = datetime.combine(day, time(end_hour), tzinfo=DAKAR)
    return start.astimezone(ZoneInfo("UTC")), end.astimezone(ZoneInfo("UTC"))
