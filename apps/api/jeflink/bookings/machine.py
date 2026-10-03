"""Machine à états de la réservation, déclarée en entier (ADR 0010) et activée par la spec 004.

Un couple déclaré avec ``enabled=False`` lèverait ``transition_not_enabled`` : la spec 004 les
active tous. Fonctions pures, sans base de données.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta

from django.conf import settings

from jeflink.common.dakar import DAKAR

from .models import Booking

Status = Booking.Status
Actor = Booking.Actor

CLIENT, PRO, SYSTEM, OPS = Actor.CLIENT, Actor.PRO, Actor.SYSTEM, Actor.OPS


@dataclass(frozen=True)
class Rule:
    actors: frozenset[str]
    enabled: bool


def _rule(*actors: str, enabled: bool = False) -> Rule:
    return Rule(frozenset(actors), enabled)


# (depuis, vers) -> qui peut la faire, et si cette spec l'active.
DECLARED: dict[tuple[str, str], Rule] = {
    (Status.ACCEPTED, Status.SCHEDULED): _rule(PRO, enabled=True),
    (Status.ACCEPTED, Status.CANCELLED): _rule(CLIENT, PRO, SYSTEM, enabled=True),
    (Status.SCHEDULED, Status.CANCELLED): _rule(CLIENT, PRO, SYSTEM, enabled=True),
    # Déroulé de l'intervention, clôture et litige (spec 004).
    (Status.SCHEDULED, Status.EN_ROUTE): _rule(PRO, enabled=True),
    (Status.EN_ROUTE, Status.ON_SITE): _rule(PRO, enabled=True),
    (Status.ON_SITE, Status.IN_PROGRESS): _rule(PRO, enabled=True),
    # Avenant accepté par le client : le statut ne change pas, l'événement trace l'accord.
    (Status.IN_PROGRESS, Status.IN_PROGRESS): _rule(CLIENT, enabled=True),
    (Status.IN_PROGRESS, Status.COMPLETED): _rule(PRO, enabled=True),
    (Status.COMPLETED, Status.CLOSED): _rule(SYSTEM, enabled=True),
    (Status.COMPLETED, Status.DISPUTED): _rule(CLIENT, enabled=True),
    (Status.DISPUTED, Status.CLOSED): _rule(OPS, enabled=True),
    # Le pro déjà parti ou arrivé peut renoncer ; le client ne peut plus annuler un pro sur place.
    (Status.EN_ROUTE, Status.CANCELLED): _rule(CLIENT, PRO, SYSTEM, enabled=True),
    (Status.ON_SITE, Status.CANCELLED): _rule(PRO, SYSTEM, enabled=True),
}

# Contact partagé (numéros des deux parties, repère et position du client) : le pro a confirmé,
# et la réservation vit encore. Jamais à ``accepted``, ni après une annulation (spec 003).
DISCLOSED_STATUSES = frozenset(
    {
        Status.SCHEDULED,
        Status.EN_ROUTE,
        Status.ON_SITE,
        Status.IN_PROGRESS,
        Status.COMPLETED,
        Status.DISPUTED,
    }
)

# --- Motifs : codes en dur, ils pilotent la fiabilité (contrairement aux libellés de données) ---
# Un désistement du pro compte à partir de ``scheduled`` ; parti ou arrivé, il est toujours tardif.
PRO_FAULT_FROM = (Status.SCHEDULED, Status.EN_ROUTE, Status.ON_SITE)
ALWAYS_LATE_FROM = (Status.EN_ROUTE, Status.ON_SITE)
PRO_NO_SHOW = "pro_no_show"  # le client déclare que le pro n'est pas venu (acteur client)
NO_SHOW_WEIGHT = 3  # poids d'un no-show, appliqué à la confirmation seulement
CLIENT_ABSENT = "client_absent"  # le pro est sur place et le client n'y est pas : poids 0, tracé


def is_late(*, slot_start: datetime, now: datetime) -> bool:
    """Annulation « tardive » : moins de 2 h avant le début du créneau, ou après."""
    return now >= slot_start - settings.BOOKING_LATE_CANCEL_WINDOW


def reliability_weight(
    *, actor_kind: str, from_status: str, to_status: str, late: bool, reason: str = ""
) -> int:
    """Poids d'un désistement dans la fiabilité d'un pro (V1 : trace seulement, pas de score).

    - Pro : rien avant ``scheduled`` (``pro_unconfirmed`` compris, c'est le système qui annule).
      Ensuite, tout désistement compte 1, et 2 s'il est tardif (toujours, une fois en route).
      ``client_absent`` (le client n'est pas là) est tracé avec un poids de 0.
    - Client : jamais rien contre le pro, ``price`` compris. Une annulation tardive du client
      est tracée (``late``), sans pénalité.
    - Système (non-confirmation, suspension) : 0.
    - ``pro_no_show`` (déclaré par le client) : 0 à la déclaration. Le poids ``NO_SHOW_WEIGHT``
      est journalisé à la confirmation (après 24 h sans contestation, ou décision de l'Ops).
    """
    if to_status != Status.CANCELLED or actor_kind != PRO:
        return 0
    if from_status not in PRO_FAULT_FROM or reason == CLIENT_ABSENT:
        return 0
    return 2 if late else 1


# --- Délai de confirmation du pro -------------------------------------------------------------


def _quiet_window(local: datetime) -> tuple[bool, datetime]:
    """(dans la plage de gel ?, prochain changement) pour un instant en heure de Dakar."""
    start_hour, end_hour = settings.BOOKING_CONFIRM_QUIET_HOURS
    day = local.replace(hour=0, minute=0, second=0, microsecond=0)
    start_today = day + timedelta(hours=start_hour)
    end_today = day + timedelta(hours=end_hour)
    if start_hour > end_hour:  # la plage passe minuit (21 h à 7 h)
        if local >= start_today:
            return True, end_today + timedelta(days=1)
        if local < end_today:
            return True, end_today
        return False, start_today
    if start_today <= local < end_today:
        return True, end_today
    if local < start_today:
        return False, start_today
    return False, start_today + timedelta(days=1)


def confirm_deadline(*, accepted_at: datetime, slot_start: datetime, urgent: bool) -> datetime:
    """Heure limite de confirmation du pro : 4 h (1 h si urgent), gelée de 21 h à 7 h (Dakar),
    et jamais après le début du créneau. Fonction pure.

    Acceptation à 20 h 30 : 30 min avant le gel, le reste (3 h 30) à partir de 7 h.
    """
    remaining = settings.BOOKING_CONFIRM_TTL_URGENT if urgent else settings.BOOKING_CONFIRM_TTL
    current = accepted_at.astimezone(DAKAR)
    while True:
        quiet, boundary = _quiet_window(current)
        if quiet:
            current = boundary
            continue
        if current + remaining <= boundary:
            deadline = current + remaining
            break
        remaining -= boundary - current
        current = boundary  # début du gel : on saute à sa fin au tour suivant
    return min(deadline, slot_start).astimezone(accepted_at.tzinfo or DAKAR)
