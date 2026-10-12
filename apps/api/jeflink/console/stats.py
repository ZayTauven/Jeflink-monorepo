"""Chiffres du tableau de bord de la console : lecture seule, calculés à la demande.

Une « période » = les N derniers jours glissants. Le volume d'affaires d'une période est la somme
des devis acceptés pour les demandes réservées pendant cette période (date de l'événement
« Pro réservé »), en F CFA entiers.
"""

from collections import Counter, defaultdict
from datetime import timedelta

from django.db.models import Count, Min, Q
from django.utils import timezone

from jeflink.accounts.models import ContactMessage, ProProfile, User
from jeflink.catalog.models import Trade, Zone
from jeflink.jobs.models import Quote, RequestEvent, Review, ServiceRequest

S = ServiceRequest.Status
STALE_AFTER = timedelta(hours=24)


def _booked(start, end) -> dict[int, int]:
    """{id de demande: montant du devis accepté} pour les réservations faites dans [start, end[."""
    ids = RequestEvent.objects.filter(
        status=S.BOOKED, created_at__gte=start, created_at__lt=end
    ).values("request_id")
    return dict(
        Quote.objects.filter(request_id__in=ids, status=Quote.Status.ACCEPTED).values_list(
            "request_id", "amount"
        )
    )


def _period(start, end) -> dict:
    created = ServiceRequest.objects.filter(created_at__gte=start, created_at__lt=end)
    total = created.count()
    booked = created.filter(status__in=[S.BOOKED, S.DONE]).count()
    hours = [
        (r.first_quote - r.created_at).total_seconds() / 3600
        for r in created.annotate(first_quote=Min("quotes__created_at")).exclude(first_quote=None)
    ]
    ratings = Review.objects.filter(created_at__gte=start, created_at__lt=end).values_list(
        "rating", flat=True
    )
    return {
        "requests": total,
        "booking_rate": round(100 * booked / total) if total else None,
        "volume": sum(_booked(start, end).values()),
        "first_quote_hours": round(sum(hours) / len(hours), 1) if hours else None,
        "rating": round(sum(ratings) / len(ratings), 1) if ratings else None,
        "reviews": len(ratings),
    }


def _pending_pros():
    """Pros inscrits que l'équipe n'a pas encore vérifiés."""
    return ProProfile.objects.filter(is_verified=False, user__is_active=True)


def _stale_requests(now):
    """Demandes ouvertes depuis plus de 24 h sans aucun devis."""
    return (
        ServiceRequest.objects.filter(status=S.OPEN, created_at__lt=now - STALE_AFTER)
        .annotate(n=Count("quotes"))
        .filter(n=0)
    )


def _person(user) -> dict:
    return {"id": user.pk, "name": user.get_full_name() or user.email, "photo": user.photo}


def overview(days: int = 30) -> dict:
    now = timezone.now()
    start = now - timedelta(days=days)
    current, previous = _period(start, now), _period(start - timedelta(days=days), start)

    # Séries quotidiennes (heure de Dakar) : demandes publiées et réservations.
    today = timezone.localdate(now)
    first_day = today - timedelta(days=days - 1)
    created_by_day = Counter(
        timezone.localdate(d)
        for d in ServiceRequest.objects.filter(created_at__gte=start).values_list(
            "created_at", flat=True
        )
    )
    booked_by_day = Counter(
        timezone.localdate(d)
        for d in RequestEvent.objects.filter(status=S.BOOKED, created_at__gte=start).values_list(
            "created_at", flat=True
        )
    )
    daily = [
        {
            "date": (day := first_day + timedelta(days=i)).isoformat(),
            "created": created_by_day[day],
            "booked": booked_by_day[day],
        }
        for i in range(days)
    ]

    # Répartition par métier et par quartier sur la période.
    booked = _booked(start, now)
    period_requests = ServiceRequest.objects.filter(created_at__gte=start)
    trade_volume: dict[int, int] = defaultdict(int)
    for trade_id, req_id in ServiceRequest.objects.filter(pk__in=booked).values_list(
        "trade_id", "pk"
    ):
        trade_volume[trade_id] += booked[req_id]
    by_trade = [
        {
            "slug": t.slug,
            "name": t.name,
            "icon": t.icon,
            "requests": t.n,
            "volume": trade_volume[t.pk],
        }
        for t in Trade.objects.annotate(
            n=Count("servicerequest", filter=Q(servicerequest__created_at__gte=start))
        )
    ]
    by_zone = [
        {"slug": z.slug, "name": z.name, "requests": z.n}
        for z in Zone.objects.annotate(
            n=Count("servicerequest", filter=Q(servicerequest__created_at__gte=start))
        )
        .filter(n__gt=0)
        .order_by("-n", "name")[:8]
    ]

    # Meilleurs pros de la période (volume réservé).
    pro_volume: dict[int, int] = defaultdict(int)
    pro_missions: Counter = Counter()
    for pro_id, req_id in ServiceRequest.objects.filter(pk__in=booked).values_list("pro_id", "pk"):
        pro_volume[pro_id] += booked[req_id]
        pro_missions[pro_id] += 1
    top_ids = sorted(pro_volume, key=pro_volume.get, reverse=True)[:5]
    profiles = {
        p.user_id: p
        for p in ProProfile.objects.filter(user_id__in=top_ids)
        .select_related("user")
        .prefetch_related("trades")
    }
    top_pros = [
        {
            **_person(profiles[pid].user),
            "photo": profiles[pid].photo or profiles[pid].user.photo,
            "trades": [t.name for t in profiles[pid].trades.all()],
            "missions": pro_missions[pid],
            "volume": pro_volume[pid],
            "rating": profiles[pid].rating(),
        }
        for pid in top_ids
        if pid in profiles
    ]

    activity = [
        {
            "id": e.pk,
            "request_id": e.request_id,
            "title": e.request.title,
            "status": e.status,
            "status_label": S(e.status).label,
            "note": e.note,
            "actor": _person(e.actor) if e.actor else None,
            "created_at": e.created_at,
        }
        for e in RequestEvent.objects.select_related("request", "actor").order_by(
            "-created_at", "-id"
        )[:10]
    ]

    pending = (
        _pending_pros()
        .select_related("user")
        .prefetch_related("trades")
        .order_by("user__date_joined")
    )
    stale = _stale_requests(now).select_related("trade", "zone")
    low_reviews = Review.objects.filter(rating__lte=2, created_at__gte=start).select_related(
        "request__pro", "request__client"
    )

    return {
        "period_days": days,
        "current": current,
        "previous": previous,
        "counts": {
            "pros": ProProfile.objects.count(),
            "pros_verified": ProProfile.objects.filter(is_verified=True).count(),
            "pros_pending": pending.count(),
            "clients": User.objects.filter(role=User.Role.CLIENT, is_staff=False).count(),
            "open_requests": ServiceRequest.objects.filter(status=S.OPEN).count(),
            "stale_requests": stale.count(),
            "contact_unhandled": ContactMessage.objects.filter(is_handled=False).count(),
        },
        "status_breakdown": [
            {"status": s.value, "label": s.label, "count": n}
            for s in S
            for n in [period_requests.filter(status=s).count()]
        ],
        "daily": daily,
        "by_trade": sorted(by_trade, key=lambda t: (-t["requests"], t["name"])),
        "by_zone": by_zone,
        "top_pros": top_pros,
        "activity": activity,
        "alerts": {
            "pending_pros": [
                {
                    **_person(p.user),
                    "trades": [t.name for t in p.trades.all()],
                    "joined_at": p.user.date_joined,
                }
                for p in pending[:5]
            ],
            "stale_requests": [
                {
                    "id": r.pk,
                    "title": r.title,
                    "trade": r.trade.name,
                    "zone": r.zone.name,
                    "created_at": r.created_at,
                }
                for r in stale.order_by("created_at")[:5]
            ],
            "low_reviews": [
                {
                    "request_id": r.request_id,
                    "rating": r.rating,
                    "comment": r.comment,
                    "pro": _person(r.request.pro) if r.request.pro else None,
                    "client": _person(r.request.client),
                    "created_at": r.created_at,
                }
                for r in low_reviews.order_by("-created_at")[:5]
            ],
        },
    }


def badges() -> dict:
    """Compteurs des pastilles du menu de la console (à traiter)."""
    return {
        "pros_pending": _pending_pros().count(),
        "stale_requests": _stale_requests(timezone.now()).count(),
        "contact_unhandled": ContactMessage.objects.filter(is_handled=False).count(),
    }
