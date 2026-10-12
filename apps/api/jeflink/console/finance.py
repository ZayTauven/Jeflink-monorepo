"""Chiffres d'argent de la console (lecture seule). Tout est en F CFA entiers.

Paiement sur place (démo) : pour une mission terminée, le client paie au pro `price - discount`,
le pro doit à Jeflink `commission`, et Jeflink doit au pro la remise `discount` qu'il finance.
Net pour Jeflink = commission - remise. Solde d'un pro = ce net cumulé, corrigé des règlements.
"""

from collections import defaultdict
from datetime import date, datetime, time, timedelta

from django.db.models import Count, F, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone

from jeflink.accounts.models import ProProfile
from jeflink.jobs.models import RequestEvent, ServiceRequest

from .models import ProSettlement

S = ServiceRequest.Status


def missions():
    """Missions réservées avec leurs montants (les annulées ne comptent pas)."""
    return (
        ServiceRequest.objects.exclude(price=None)
        .exclude(status=S.CANCELLED)
        .select_related("trade", "zone", "client", "pro", "coupon")
    )


def totals(qs) -> dict:
    agg = qs.aggregate(
        count=Count("id"),
        volume=Coalesce(Sum("price"), 0),
        discount=Coalesce(Sum("discount"), 0),
        commission=Coalesce(Sum("commission"), 0),
    )
    agg["client_paid"] = agg["volume"] - agg["discount"]
    agg["net"] = agg["commission"] - agg["discount"]
    return agg


def done_dates(ids) -> dict[int, datetime]:
    """Date de fin de chaque mission terminée (événement « Terminée »)."""
    return dict(
        RequestEvent.objects.filter(request_id__in=ids, status=S.DONE).values_list(
            "request_id", "created_at"
        )
    )


def day_start(d: date) -> datetime:
    return timezone.make_aware(datetime.combine(d, time.min))


# --- Soldes des pros ---------------------------------------------------------------------------


def balances() -> list[dict]:
    """Un solde par pro ayant des missions terminées ou des règlements, du plus gros au plus petit.

    balance > 0 : le pro doit cette somme à Jeflink ; balance < 0 : Jeflink la doit au pro.
    """
    due = defaultdict(int)
    count = defaultdict(int)
    for pro_id, commission, discount in ServiceRequest.objects.filter(
        status=S.DONE, pro__isnull=False
    ).values_list("pro_id", "commission", "discount"):
        due[pro_id] += commission - discount
        count[pro_id] += 1
    paid = defaultdict(int)
    for s in ProSettlement.objects.all().only("pro_id", "direction", "amount"):
        paid[s.pro_id] += s.signed
    profiles = {
        p.user_id: p
        for p in ProProfile.objects.filter(user_id__in=set(due) | set(paid)).select_related("user")
    }
    rows = [
        {
            "pro": profile,
            "missions_done": count[pid],
            "due": due[pid],
            "settled": -paid[pid],
            "balance": due[pid] + paid[pid],
        }
        for pid, profile in profiles.items()
    ]
    return sorted(rows, key=lambda r: (-abs(r["balance"]), r["pro"].user.get_full_name()))


def pro_balance(pro) -> dict:
    done = ServiceRequest.objects.filter(status=S.DONE, pro=pro)
    agg = done.aggregate(due=Coalesce(Sum(F("commission") - F("discount")), 0), n=Count("id"))
    settled = sum(s.signed for s in ProSettlement.objects.filter(pro=pro))
    return {
        "missions_done": agg["n"],
        "due": agg["due"],
        "settled": -settled,
        "balance": agg["due"] + settled,
    }


# --- Rapport mensuel ---------------------------------------------------------------------------


def month_bounds(year: int, month: int) -> tuple[datetime, datetime]:
    start = day_start(date(year, month, 1))
    nxt = date(year + (month == 12), month % 12 + 1, 1)
    return start, day_start(nxt)


def monthly(months: int = 6) -> list[dict]:
    """Les `months` derniers mois (le mois en cours d'abord), sur la date de fin des missions."""
    today = timezone.localdate()
    out = []
    year, month = today.year, today.month
    for _ in range(months):
        start, end = month_bounds(year, month)
        done_ids = RequestEvent.objects.filter(
            status=S.DONE, created_at__gte=start, created_at__lt=end
        ).values("request_id")
        created = ServiceRequest.objects.filter(created_at__gte=start, created_at__lt=end)
        out.append(
            {
                "month": f"{year:04d}-{month:02d}",
                "requests": created.count(),
                "booked": created.filter(status__in=[S.BOOKED, S.DONE]).count(),
                **totals(missions().filter(pk__in=done_ids)),
                "coupons_used": missions().filter(pk__in=done_ids, coupon__isnull=False).count(),
            }
        )
        year, month = (year - 1, 12) if month == 1 else (year, month - 1)
    return out


def by_trade(year: int, month: int) -> list[dict]:
    start, end = month_bounds(year, month)
    done_ids = RequestEvent.objects.filter(
        status=S.DONE, created_at__gte=start, created_at__lt=end
    ).values("request_id")
    rows = (
        missions()
        .filter(pk__in=done_ids)
        .values("trade__name", "trade__icon")
        .annotate(
            count=Count("id"),
            volume=Coalesce(Sum("price"), 0),
            discount=Coalesce(Sum("discount"), 0),
            commission=Coalesce(Sum("commission"), 0),
        )
        .order_by("-volume")
    )
    return [
        {
            "trade": r["trade__name"],
            "icon": r["trade__icon"],
            "count": r["count"],
            "volume": r["volume"],
            "discount": r["discount"],
            "commission": r["commission"],
            "net": r["commission"] - r["discount"],
        }
        for r in rows
    ]


def period_filter(qs, days: int | None, trade: str = "", pro: str = "", coupon: str = ""):
    """Filtres de la page Transactions (sur la date de réservation)."""
    if days:
        booked = RequestEvent.objects.filter(
            status=S.BOOKED, created_at__gte=timezone.now() - timedelta(days=days)
        ).values("request_id")
        qs = qs.filter(pk__in=booked)
    if trade:
        qs = qs.filter(trade__slug=trade)
    if pro.isdigit():
        qs = qs.filter(pro_id=int(pro))
    if coupon:
        qs = qs.filter(coupon__code=coupon.upper()) if coupon != "*" else qs.exclude(coupon=None)
    return qs
