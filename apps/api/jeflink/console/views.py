"""API de la console d'administration : réservée à l'équipe Jeflink (comptes ``is_staff``).

Lecture : listes filtrées et paginées (20 par page), fiches détaillées.
Écriture : actions explicites (vérifier, suspendre, masquer…) qui passent par ``services`` et sont
journalisées. Aucune modification libre d'un enregistrement.
"""

import csv
from datetime import timedelta

from django.conf import settings
from django.db.models import Count, F, IntegerField, Max, OuterRef, Q, Subquery, Sum, Value
from django.db.models.functions import Coalesce
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.exceptions import ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

from jeflink.accounts.models import ContactMessage, ProProfile, User
from jeflink.catalog.models import Campaign, City, Trade, Zone
from jeflink.jef import ai as jef_ai
from jeflink.jef.models import JefSession
from jeflink.jobs.models import Coupon, Dispute, Quote, Review, ServiceRequest

from . import finance, services, stats
from . import serializers as s
from .models import AuditLog, PlatformSettings, ProSettlement
from .permissions import ConsoleSection, can, section

PERIODS = {7, 30, 90}
S = ServiceRequest.Status
ACTIVE_DISPUTE = [Dispute.Status.OPEN, Dispute.Status.INVESTIGATING]


@extend_schema(
    parameters=[OpenApiParameter("days", int, description="Période : 7, 30 ou 90 jours")],
    responses=OpenApiTypes.OBJECT,
)
@api_view(["GET"])
@permission_classes([section("dashboard")])
def overview(request):
    """Tableau de bord : indicateurs de la période et de la précédente, séries, alertes."""
    try:
        days = int(request.query_params.get("days", 30))
    except ValueError:
        days = 30
    data = stats.overview(days if days in PERIODS else 30)
    if not can(request.user, "operations"):
        # Noms, avis et activité détaillée : réservés aux rôles qui traitent les opérations.
        for key in ("alerts", "activity", "top_pros"):
            data.pop(key, None)
    return Response(data)


@extend_schema(responses=OpenApiTypes.OBJECT)
@api_view(["GET"])
@permission_classes([section("dashboard")])
def badges(request):
    """Compteurs du menu : pros à vérifier, demandes sans devis, messages non traités."""
    return Response(stats.badges())


# --- Socle -------------------------------------------------------------------------------------


class ConsolePagination(PageNumberPagination):
    page_size = 20


class ConsoleViewSet(viewsets.GenericViewSet):
    permission_classes = [ConsoleSection]
    console_section = "operations"  # rubrique de la console (voir permissions.py)
    pagination_class = ConsolePagination

    def param(self, name: str) -> str:
        return (self.request.query_params.get(name) or "").strip()

    def sort(self, queryset, choices: dict, default: tuple):
        """Tri demandé (`sort`), pris dans une liste blanche ; sinon `default`."""
        return queryset.order_by(*choices.get(self.param("sort"), default))

    def paginated(self, queryset, serializer_class, facets: dict | None = None):
        page = self.paginate_queryset(queryset)
        response = self.get_paginated_response(serializer_class(page, many=True).data)
        if facets is not None:
            response.data["facets"] = facets
        return response

    def done(self, obj, serializer_class):
        """Réponse d'une action : l'objet relu à jour."""
        return Response(serializer_class(obj).data)


def search_people(prefix: str, q: str) -> Q:
    """Recherche sur nom, prénom, email et téléphone d'un compte (préfixe de relation)."""
    query = Q()
    for word in q.split():
        query &= (
            Q(**{f"{prefix}first_name__icontains": word})
            | Q(**{f"{prefix}last_name__icontains": word})
            | Q(**{f"{prefix}email__icontains": word})
            | Q(**{f"{prefix}phone__icontains": word})
        )
    return query


# --- Demandes ----------------------------------------------------------------------------------


def requests_queryset():
    accepted = Quote.objects.filter(request=OuterRef("pk"), status=Quote.Status.ACCEPTED)
    return ServiceRequest.objects.select_related("trade", "zone", "client", "pro").annotate(
        n_quotes=Count("quotes", distinct=True),
        n_open_disputes=Count(
            "disputes", filter=Q(disputes__status__in=ACTIVE_DISPUTE), distinct=True
        ),
        accepted_amount=Subquery(accepted.values("amount")[:1]),
    )


REQUEST_SORTS = {
    "recent": ("-created_at",),
    "oldest": ("created_at",),
    "amount": (F("accepted_amount").desc(nulls_last=True), "-created_at"),
}


@extend_schema(
    parameters=[
        OpenApiParameter("status", str, enum=[v for v in S.values]),
        OpenApiParameter("trade", str, description="slug du métier"),
        OpenApiParameter("zone", str, description="slug du quartier"),
        OpenApiParameter("q", str, description="n°, titre, client ou pro"),
        OpenApiParameter("urgent", bool),
        OpenApiParameter("stale", bool, description="ouvertes depuis 24 h sans devis"),
        OpenApiParameter("dispute", bool, description="avec un litige en cours"),
        OpenApiParameter("sort", str, enum=["recent", "oldest", "amount"]),
    ]
)
class RequestConsoleViewSet(ConsoleViewSet):
    """Demandes : toutes, filtrables ; fiche complète ; annulation, note interne, litige."""

    serializer_class = s.RequestRowSerializer

    def get_queryset(self):
        return requests_queryset()

    def list(self, request):
        qs = self.get_queryset()
        if status := self.param("status"):
            qs = qs.filter(status=status)
        if trade := self.param("trade"):
            qs = qs.filter(trade__slug=trade)
        if zone := self.param("zone"):
            qs = qs.filter(zone__slug=zone)
        if self.param("urgent") == "1":
            qs = qs.filter(is_urgent=True)
        if self.param("stale") == "1":
            qs = qs.filter(
                status=S.OPEN, created_at__lt=timezone.now() - stats.stale_after(), n_quotes=0
            )
        if self.param("dispute") == "1":
            qs = qs.filter(n_open_disputes__gt=0)
        if q := self.param("q"):
            query = Q(title__icontains=q) | search_people("client__", q) | search_people("pro__", q)
            if q.lstrip("#").isdigit():
                query |= Q(pk=int(q.lstrip("#")))
            qs = qs.filter(query)
        facets = {
            v: n
            for v, n in ServiceRequest.objects.values_list("status")
            .annotate(n=Count("id"))
            .values_list("status", "n")
        }
        return self.paginated(
            self.sort(qs, REQUEST_SORTS, ("-created_at",)), s.RequestRowSerializer, facets
        )

    def retrieve(self, request, pk=None):
        req = get_object_or_404(
            self.get_queryset().prefetch_related(
                "quotes__pro",
                "events__actor",
                "disputes__opened_by",
                "disputes__handled_by",
                "disputes__request__client",
                "disputes__request__pro",
            ),
            pk=pk,
        )
        return Response(s.RequestDetailSerializer(req).data)

    def _reload(self, pk):
        return self.retrieve(self.request, pk)

    @extend_schema(request=s.CallNoteSerializer, responses=s.RequestDetailSerializer)
    @action(detail=True, methods=["post"], url_path="confirm-cancel")
    def confirm_cancel(self, request, pk=None):
        """Annulation demandée par le client : confirmée après l'appel du support."""
        return self._after_call(request, pk, services.confirm_cancel)

    @extend_schema(request=s.CallNoteSerializer, responses=s.RequestDetailSerializer)
    @action(detail=True, methods=["post"], url_path="keep")
    def keep(self, request, pk=None):
        """Annulation demandée par le client : la mission est maintenue après l'appel."""
        return self._after_call(request, pk, services.keep_mission)

    def _after_call(self, request, pk, decide):
        data = s.CallNoteSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        decide(request.user, get_object_or_404(ServiceRequest, pk=pk), data.validated_data["note"])
        return self._reload(pk)

    @extend_schema(request=s.ReasonSerializer, responses=s.RequestDetailSerializer)
    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        data = s.ReasonSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        services.cancel_request(
            request.user, get_object_or_404(ServiceRequest, pk=pk), data.validated_data["reason"]
        )
        return self._reload(pk)

    @extend_schema(request=s.NoteSerializer, responses=s.RequestDetailSerializer)
    @action(detail=True, methods=["post"])
    def note(self, request, pk=None):
        data = s.NoteSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        services.set_staff_note(
            request.user, get_object_or_404(ServiceRequest, pk=pk), data.validated_data["note"]
        )
        return self._reload(pk)

    @extend_schema(request=s.DisputeOpenSerializer, responses=s.RequestDetailSerializer)
    @action(detail=True, methods=["post"])
    def disputes(self, request, pk=None):
        data = s.DisputeOpenSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        services.open_dispute(
            request.user, get_object_or_404(ServiceRequest, pk=pk), **data.validated_data
        )
        return self._reload(pk)


# --- Litiges -----------------------------------------------------------------------------------


@extend_schema(
    parameters=[
        OpenApiParameter("status", str, enum=Dispute.Status.values),
        OpenApiParameter("active", bool, description="ouverts ou en cours"),
    ]
)
class DisputeConsoleViewSet(ConsoleViewSet):
    serializer_class = s.DisputeSerializer

    def get_queryset(self):
        return Dispute.objects.select_related(
            "request", "request__client", "request__pro", "opened_by", "handled_by"
        )

    def list(self, request):
        qs = self.get_queryset()
        if status := self.param("status"):
            qs = qs.filter(status=status)
        if self.param("active") == "1":
            qs = qs.filter(status__in=ACTIVE_DISPUTE)
        facets = dict(Dispute.objects.values_list("status").annotate(n=Count("id")))
        return self.paginated(qs.order_by("-created_at"), s.DisputeSerializer, facets)

    def retrieve(self, request, pk=None):
        return Response(s.DisputeSerializer(get_object_or_404(self.get_queryset(), pk=pk)).data)

    @extend_schema(request=s.DisputeUpdateSerializer, responses=s.DisputeSerializer)
    @action(detail=True, methods=["post"], url_path="status")
    def set_status(self, request, pk=None):
        data = s.DisputeUpdateSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        dispute = services.update_dispute(
            request.user,
            get_object_or_404(Dispute, pk=pk),
            data.validated_data["status"],
            data.validated_data.get("resolution", ""),
        )
        return self.done(self.get_queryset().get(pk=dispute.pk), s.DisputeSerializer)


# --- Pros --------------------------------------------------------------------------------------

PRO_SORTS = {
    "name": ("user__first_name", "user__last_name"),
    "missions": ("-n_done", "user__first_name"),
    "recent": ("-user__date_joined",),
}


@extend_schema(
    parameters=[
        OpenApiParameter("status", str, enum=["pending", "verified", "suspended"]),
        OpenApiParameter("trade", str),
        OpenApiParameter("q", str),
        OpenApiParameter("sort", str, enum=["name", "missions", "recent"]),
    ]
)
class ProConsoleViewSet(ConsoleViewSet):
    """Pros : file de vérification, fiches, vérification, refus, suspension."""

    serializer_class = s.ProRowSerializer

    def get_queryset(self):
        return (
            ProProfile.objects.filter(user__is_staff=False)
            .select_related("user")
            .prefetch_related("trades", "zones")
            .annotate(n_done=Count("user__missions", filter=Q(user__missions__status=S.DONE)))
        )

    def list(self, request):
        qs = self.get_queryset()
        status = self.param("status")
        if status == "pending":
            qs = qs.filter(is_verified=False, user__is_active=True)
        elif status == "verified":
            qs = qs.filter(is_verified=True, user__is_active=True)
        elif status == "suspended":
            qs = qs.filter(user__is_active=False)
        if trade := self.param("trade"):
            qs = qs.filter(trades__slug=trade)
        if q := self.param("q"):
            qs = qs.filter(search_people("user__", q) | Q(headline__icontains=q))
        # File d'attente : les plus anciens inscrits d'abord ; sinon par nom.
        default = ("user__date_joined",) if status == "pending" else PRO_SORTS["name"]
        qs = self.sort(qs, PRO_SORTS, default)
        base = ProProfile.objects
        facets = {
            "pending": base.filter(is_verified=False, user__is_active=True).count(),
            "verified": base.filter(is_verified=True, user__is_active=True).count(),
            "suspended": base.filter(user__is_active=False).count(),
        }
        return self.paginated(qs.distinct(), s.ProRowSerializer, facets)

    def _profile(self, pk) -> ProProfile:
        return get_object_or_404(self.get_queryset(), user_id=pk)

    def retrieve(self, request, pk=None):
        profile = self._profile(pk)
        user = profile.user
        quotes = Quote.objects.filter(pro=user)
        volume = quotes.filter(status=Quote.Status.ACCEPTED, request__status=S.DONE).aggregate(
            v=Sum("amount")
        )["v"]
        missions = requests_queryset().filter(pro=user).order_by("-created_at")[:10]
        reviews = (
            Review.objects.filter(request__pro=user)
            .select_related("request__client", "request__pro", "request__trade")
            .order_by("-created_at")[:10]
        )
        disputes = Dispute.objects.filter(request__pro=user).select_related(
            "request", "request__client", "request__pro", "opened_by", "handled_by"
        )[:10]
        return Response(
            {
                **s.ProRowSerializer(profile).data,
                "bio": profile.bio,
                "stats": {
                    "quotes_sent": quotes.count(),
                    "quotes_accepted": quotes.filter(status=Quote.Status.ACCEPTED).count(),
                    "volume": volume or 0,
                },
                "missions": s.RequestRowSerializer(missions, many=True).data,
                "reviews": s.ReviewRowSerializer(reviews, many=True).data,
                "disputes": s.DisputeSerializer(disputes, many=True).data,
            }
        )

    @extend_schema(request=None, responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["post"])
    def verify(self, request, pk=None):
        services.verify_pro(request.user, self._profile(pk))
        return self.retrieve(request, pk)

    @extend_schema(request=s.ReasonSerializer, responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        data = s.ReasonSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        services.reject_pro(request.user, self._profile(pk), data.validated_data["reason"])
        return self.retrieve(request, pk)

    @extend_schema(request=s.ReasonSerializer, responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["post"])
    def suspend(self, request, pk=None):
        data = s.ReasonSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        services.suspend_user(request.user, self._profile(pk).user, data.validated_data["reason"])
        return self.retrieve(request, pk)

    @extend_schema(request=None, responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["post"])
    def reactivate(self, request, pk=None):
        services.reactivate_user(request.user, self._profile(pk).user)
        return self.retrieve(request, pk)


# --- Clients -----------------------------------------------------------------------------------


@extend_schema(
    parameters=[
        OpenApiParameter("status", str, enum=["active", "suspended"]),
        OpenApiParameter("q", str),
    ]
)
class ClientConsoleViewSet(ConsoleViewSet):
    """Clients : comptes, demandes, dépenses ; suspension."""

    serializer_class = s.ClientRowSerializer

    def get_queryset(self):
        spent = (
            Quote.objects.filter(
                request__client=OuterRef("pk"),
                status=Quote.Status.ACCEPTED,
                request__status=S.DONE,
            )
            .values("request__client")
            .annotate(total=Sum("amount"))
            .values("total")
        )
        return User.objects.filter(role=User.Role.CLIENT, is_staff=False).annotate(
            n_requests=Count("requests", distinct=True),
            last_request_at=Max("requests__created_at"),
            spent=Coalesce(Subquery(spent, output_field=IntegerField()), Value(0)),
        )

    def list(self, request):
        qs = self.get_queryset()
        status = self.param("status")
        if status == "active":
            qs = qs.filter(is_active=True)
        elif status == "suspended":
            qs = qs.filter(is_active=False)
        if q := self.param("q"):
            qs = qs.filter(search_people("", q))
        base = User.objects.filter(role=User.Role.CLIENT, is_staff=False)
        facets = {
            "active": base.filter(is_active=True).count(),
            "suspended": base.filter(is_active=False).count(),
        }
        return self.paginated(qs.order_by("-date_joined"), s.ClientRowSerializer, facets)

    def _client(self, pk) -> User:
        return get_object_or_404(self.get_queryset(), pk=pk)

    def retrieve(self, request, pk=None):
        client = self._client(pk)
        reqs = requests_queryset().filter(client=client).order_by("-created_at")[:20]
        reviews = (
            Review.objects.filter(request__client=client)
            .select_related("request__client", "request__pro", "request__trade")
            .order_by("-created_at")[:10]
        )
        disputes = Dispute.objects.filter(request__client=client).select_related(
            "request", "request__client", "request__pro", "opened_by", "handled_by"
        )[:10]
        return Response(
            {
                **s.ClientRowSerializer(client).data,
                "requests": s.RequestRowSerializer(reqs, many=True).data,
                "reviews": s.ReviewRowSerializer(reviews, many=True).data,
                "disputes": s.DisputeSerializer(disputes, many=True).data,
            }
        )

    @extend_schema(request=s.ReasonSerializer, responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["post"])
    def suspend(self, request, pk=None):
        data = s.ReasonSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        services.suspend_user(request.user, self._client(pk), data.validated_data["reason"])
        return self.retrieve(request, pk)

    @extend_schema(request=None, responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["post"])
    def reactivate(self, request, pk=None):
        services.reactivate_user(request.user, self._client(pk))
        return self.retrieve(request, pk)


# --- Avis --------------------------------------------------------------------------------------


@extend_schema(
    parameters=[
        OpenApiParameter("rating", int),
        OpenApiParameter("low", bool, description="2/5 ou moins"),
        OpenApiParameter("hidden", bool),
        OpenApiParameter("q", str),
    ]
)
class ReviewConsoleViewSet(ConsoleViewSet):
    """Avis : modération (masquer un avis abusif, le rétablir)."""

    serializer_class = s.ReviewRowSerializer

    def get_queryset(self):
        return Review.objects.select_related("request__client", "request__pro", "request__trade")

    def list(self, request):
        qs = self.get_queryset()
        if (rating := self.param("rating")).isdigit():
            qs = qs.filter(rating=int(rating))
        if self.param("low") == "1":
            qs = qs.filter(rating__lte=2)
        if (hidden := self.param("hidden")) in ("0", "1"):
            qs = qs.filter(is_hidden=hidden == "1")
        if q := self.param("q"):
            qs = qs.filter(
                Q(comment__icontains=q)
                | search_people("request__client__", q)
                | search_people("request__pro__", q)
            )
        facets = {
            "all": Review.objects.count(),
            "low": Review.objects.filter(rating__lte=2).count(),
            "hidden": Review.objects.filter(is_hidden=True).count(),
        }
        return self.paginated(qs.order_by("-created_at"), s.ReviewRowSerializer, facets)

    @extend_schema(request=s.ReasonSerializer, responses=s.ReviewRowSerializer)
    @action(detail=True, methods=["post"])
    def hide(self, request, pk=None):
        data = s.ReasonSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        review = services.hide_review(
            request.user,
            get_object_or_404(self.get_queryset(), pk=pk),
            data.validated_data["reason"],
        )
        return self.done(review, s.ReviewRowSerializer)

    @extend_schema(request=None, responses=s.ReviewRowSerializer)
    @action(detail=True, methods=["post"])
    def show(self, request, pk=None):
        review = services.show_review(request.user, get_object_or_404(self.get_queryset(), pk=pk))
        return self.done(review, s.ReviewRowSerializer)


# --- Messages de contact -----------------------------------------------------------------------


@extend_schema(parameters=[OpenApiParameter("handled", bool)])
class ContactConsoleViewSet(ConsoleViewSet):
    serializer_class = s.ContactRowSerializer

    def get_queryset(self):
        return ContactMessage.objects.select_related("handled_by")

    def list(self, request):
        qs = self.get_queryset()
        if (handled := self.param("handled")) in ("0", "1"):
            qs = qs.filter(is_handled=handled == "1")
        facets = {
            "todo": ContactMessage.objects.filter(is_handled=False).count(),
            "done": ContactMessage.objects.filter(is_handled=True).count(),
        }
        return self.paginated(
            qs.order_by("is_handled", "-created_at"), s.ContactRowSerializer, facets
        )

    @extend_schema(request=None, responses=s.ContactRowSerializer)
    @action(detail=True, methods=["post"])
    def handle(self, request, pk=None):
        message = services.set_contact_handled(
            request.user, get_object_or_404(ContactMessage, pk=pk), True
        )
        return self.done(message, s.ContactRowSerializer)

    @extend_schema(request=None, responses=s.ContactRowSerializer)
    @action(detail=True, methods=["post"])
    def reopen(self, request, pk=None):
        message = services.set_contact_handled(
            request.user, get_object_or_404(ContactMessage, pk=pk), False
        )
        return self.done(message, s.ContactRowSerializer)


# --- Journal d'audit ---------------------------------------------------------------------------


@extend_schema(
    parameters=[
        OpenApiParameter("action", str, enum=AuditLog.Action.values),
        OpenApiParameter("target_type", str),
        OpenApiParameter("target_id", int),
        OpenApiParameter("days", int),
    ]
)
class AuditConsoleViewSet(mixins.ListModelMixin, ConsoleViewSet):
    serializer_class = s.AuditRowSerializer

    def get_queryset(self):
        qs = AuditLog.objects.select_related("actor")
        if not can(self.request.user, "admin"):
            qs = qs.exclude(target_type__in=["staff", "settings"])
        if act := self.param("action"):
            qs = qs.filter(action=act)
        if target := self.param("target_type"):
            qs = qs.filter(target_type=target)
        if (target_id := self.param("target_id")).isdigit() and len(target_id) <= 9:
            qs = qs.filter(target_id=int(target_id))
        if (days := self.param("days")).isdigit() and len(days) <= 4:
            qs = qs.filter(created_at__gte=timezone.now() - timedelta(days=int(days)))
        return qs


# --- Catalogue : métiers et quartiers ----------------------------------------------------------


def _recent():
    return timezone.now() - timedelta(days=30)


class TradeConsoleViewSet(ConsoleViewSet):
    """Métiers : tous (actifs ou non), création, modification. Pas de suppression."""

    console_section = "catalog"
    serializer_class = s.TradeConsoleSerializer
    pagination_class = None

    def get_queryset(self):
        return Trade.objects.annotate(
            n_pros=Count(
                "pros",
                filter=Q(pros__is_verified=True, pros__user__is_active=True),
                distinct=True,
            ),
            n_recent=Count(
                "servicerequest",
                filter=Q(servicerequest__created_at__gte=_recent()),
                distinct=True,
            ),
            n_total=Count("servicerequest", distinct=True),
        ).order_by("position", "name")

    def list(self, request):
        return Response(s.TradeConsoleSerializer(self.get_queryset(), many=True).data)

    def retrieve(self, request, pk=None):
        trade = get_object_or_404(self.get_queryset(), pk=pk)
        return Response(s.TradeConsoleSerializer(trade).data)

    @extend_schema(request=s.TradeInputSerializer, responses={201: s.TradeConsoleSerializer})
    def create(self, request):
        data = s.TradeInputSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        trade = services.save_trade(request.user, data.validated_data)
        return Response(
            s.TradeConsoleSerializer(self.get_queryset().get(pk=trade.pk)).data, status=201
        )

    @extend_schema(request=s.TradeInputSerializer, responses=s.TradeConsoleSerializer)
    @action(detail=True, methods=["post"], url_path="update")
    def edit(self, request, pk=None):
        data = s.TradeInputSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        services.save_trade(request.user, data.validated_data, get_object_or_404(Trade, pk=pk))
        return self.retrieve(request, pk)


class ZoneConsoleViewSet(ConsoleViewSet):
    """Quartiers desservis : ajout, modification, ouverture et fermeture."""

    console_section = "catalog"
    serializer_class = s.ZoneConsoleSerializer
    pagination_class = None

    def get_queryset(self):
        return (
            Zone.objects.annotate(
                n_pros=Count(
                    "pros",
                    filter=Q(pros__is_verified=True, pros__user__is_active=True),
                    distinct=True,
                ),
                n_recent=Count(
                    "servicerequest",
                    filter=Q(servicerequest__created_at__gte=_recent()),
                    distinct=True,
                ),
            )
            .select_related("city")
            .order_by("city__position", "city__name", "position", "name")
        )

    def list(self, request):
        return Response(s.ZoneConsoleSerializer(self.get_queryset(), many=True).data)

    @extend_schema(request=s.ZoneInputSerializer, responses={201: s.ZoneConsoleSerializer})
    def create(self, request):
        data = s.ZoneInputSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        zone = services.save_zone(request.user, data.validated_data)
        zone = self.get_queryset().get(pk=zone.pk)
        return Response(s.ZoneConsoleSerializer(zone).data, status=201)

    @extend_schema(request=s.ZoneInputSerializer, responses=s.ZoneConsoleSerializer)
    @action(detail=True, methods=["post"], url_path="update")
    def edit(self, request, pk=None):
        data = s.ZoneInputSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        zone = get_object_or_404(Zone, pk=pk)
        services.save_zone(request.user, data.validated_data, zone)
        return Response(s.ZoneConsoleSerializer(self.get_queryset().get(pk=zone.pk)).data)


class CityConsoleViewSet(ConsoleViewSet):
    """Villes desservies (rattachées à leur région) : ajout, modification, ouverture."""

    console_section = "catalog"
    serializer_class = s.CityConsoleSerializer
    pagination_class = None

    def get_queryset(self):
        return City.objects.annotate(
            n_zones=Count("zones", distinct=True),
            n_open=Count("zones", filter=Q(zones__is_active=True), distinct=True),
        )

    def list(self, request):
        return Response(s.CityConsoleSerializer(self.get_queryset(), many=True).data)

    @extend_schema(request=s.CityInputSerializer, responses={201: s.CityConsoleSerializer})
    def create(self, request):
        data = s.CityInputSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        city = services.save_city(request.user, data.validated_data)
        return Response(
            s.CityConsoleSerializer(self.get_queryset().get(pk=city.pk)).data, status=201
        )

    @extend_schema(request=s.CityInputSerializer, responses=s.CityConsoleSerializer)
    @action(detail=True, methods=["post"], url_path="update")
    def edit(self, request, pk=None):
        data = s.CityInputSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        city = get_object_or_404(City, pk=pk)
        services.save_city(request.user, data.validated_data, city)
        return Response(s.CityConsoleSerializer(self.get_queryset().get(pk=city.pk)).data)


# --- Réglages de la plateforme -----------------------------------------------------------------


@extend_schema(methods=["GET"], responses=s.SettingsSerializer)
@extend_schema(methods=["POST"], request=s.SettingsSerializer, responses=s.SettingsSerializer)
@api_view(["GET", "POST"])
@permission_classes([section("admin")])
def platform_settings(request):
    """Réglages de la plateforme. POST : tous les champs (formulaire complet)."""
    current = PlatformSettings.load()
    if request.method == "POST":
        data = s.SettingsSerializer(current, data=request.data)
        data.is_valid(raise_exception=True)
        current = services.update_settings(request.user, dict(data.validated_data))
    return Response(s.SettingsSerializer(current).data)


# --- Équipe ------------------------------------------------------------------------------------


class TeamConsoleViewSet(ConsoleViewSet):
    """Membres de l'équipe (comptes is_staff) et leur rôle dans la console."""

    console_section = "admin"
    serializer_class = s.MemberSerializer
    pagination_class = None

    def get_queryset(self):
        return User.objects.filter(is_staff=True).order_by("-is_active", "first_name", "email")

    def list(self, request):
        return Response(s.MemberSerializer(self.get_queryset(), many=True).data)

    def _member(self, pk) -> User:
        return get_object_or_404(self.get_queryset(), pk=pk)

    @extend_schema(request=s.MemberCreateSerializer, responses={201: s.MemberSerializer})
    def create(self, request):
        data = s.MemberCreateSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        member = services.add_member(request.user, data.validated_data)
        return Response(s.MemberSerializer(member).data, status=201)

    @extend_schema(request=s.RoleSerializer, responses=s.MemberSerializer)
    @action(detail=True, methods=["post"])
    def role(self, request, pk=None):
        data = s.RoleSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        member = services.set_member_role(
            request.user, self._member(pk), data.validated_data["role"]
        )
        return self.done(member, s.MemberSerializer)

    @extend_schema(request=None, responses=s.MemberSerializer)
    @action(detail=True, methods=["post"])
    def deactivate(self, request, pk=None):
        note = str(request.data.get("note", ""))[:300]
        member = services.set_member_active(request.user, self._member(pk), False, note)
        return self.done(member, s.MemberSerializer)

    @extend_schema(request=None, responses=s.MemberSerializer)
    @action(detail=True, methods=["post"])
    def reactivate(self, request, pk=None):
        member = services.set_member_active(request.user, self._member(pk), True)
        return self.done(member, s.MemberSerializer)

    @extend_schema(
        request={"multipart/form-data": OpenApiTypes.OBJECT},
        responses=s.MemberSerializer,
        description="Champ « photo » : la remplace ; « remove=1 » sans fichier : la retire.",
    )
    @action(detail=True, methods=["post"])
    def photo(self, request, pk=None):
        upload = request.FILES.get("photo")
        if not upload and request.data.get("remove") != "1":
            raise ValidationError({"photo": "Choisissez une image."})
        member = services.set_member_photo(request.user, self._member(pk), upload)
        return self.done(member, s.MemberSerializer)


# --- Marketing : codes promo et campagnes ------------------------------------------------------


def _coupons():
    used = ~Q(requests__status=S.CANCELLED)
    return Coupon.objects.prefetch_related("trades", "zones").annotate(
        n_uses=Count("requests", filter=used & Q(requests__isnull=False), distinct=True),
        sum_discount=Coalesce(Sum("requests__discount", filter=used), 0),
    )


class CouponConsoleViewSet(ConsoleViewSet):
    """Codes promo : remise en % (avec plafond) ou en F CFA, financée par Jeflink."""

    console_section = "marketing"
    serializer_class = s.CouponSerializer
    pagination_class = None

    def get_queryset(self):
        return _coupons()

    def list(self, request):
        return Response(s.CouponSerializer(self.get_queryset(), many=True).data)

    def retrieve(self, request, pk=None):
        return Response(s.CouponSerializer(get_object_or_404(self.get_queryset(), pk=pk)).data)

    @extend_schema(request=s.CouponInputSerializer, responses={201: s.CouponSerializer})
    def create(self, request):
        data = s.CouponInputSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        coupon = services.save_coupon(request.user, data.validated_data)
        return Response(s.CouponSerializer(self.get_queryset().get(pk=coupon.pk)).data, status=201)

    @extend_schema(request=s.CouponInputSerializer, responses=s.CouponSerializer)
    @action(detail=True, methods=["post"], url_path="update")
    def edit(self, request, pk=None):
        coupon = get_object_or_404(Coupon, pk=pk)
        data = s.CouponInputSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        if data.validated_data["code"] != coupon.code:
            raise ValidationError({"code": "Le code d'un code promo ne change pas."})
        services.save_coupon(request.user, data.validated_data, coupon)
        return self.retrieve(request, pk)


class CampaignConsoleViewSet(ConsoleViewSet):
    """Campagnes : bandeaux sur l'accueil ou le formulaire de demande, sur une période."""

    console_section = "marketing"
    serializer_class = s.CampaignSerializer
    pagination_class = None

    def get_queryset(self):
        return Campaign.objects.select_related("coupon")

    def list(self, request):
        return Response(s.CampaignSerializer(self.get_queryset(), many=True).data)

    @extend_schema(request=s.CampaignInputSerializer, responses={201: s.CampaignSerializer})
    def create(self, request):
        data = s.CampaignInputSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        campaign = services.save_campaign(request.user, data.validated_data)
        return Response(s.CampaignSerializer(campaign).data, status=201)

    @extend_schema(request=s.CampaignInputSerializer, responses=s.CampaignSerializer)
    @action(detail=True, methods=["post"], url_path="update")
    def edit(self, request, pk=None):
        data = s.CampaignInputSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        campaign = services.save_campaign(
            request.user, data.validated_data, get_object_or_404(Campaign, pk=pk)
        )
        return Response(s.CampaignSerializer(campaign).data)


# --- Finance -------------------------------------------------------------------------------------


def _cell(value):
    """Texte saisi par un client ou un pro : jamais lu comme une formule par Excel."""
    if isinstance(value, str) and value.lstrip()[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + value
    return value


def _csv(filename: str, header: list[str], rows) -> HttpResponse:
    """CSV pour Excel en français : séparateur « ; », UTF-8 avec BOM."""
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    response.write("\ufeff")  # BOM : Excel lit alors l'UTF-8 (accents)
    writer = csv.writer(response, delimiter=";")
    writer.writerow(header)
    writer.writerows([_cell(v) for v in row] for row in rows)
    return response


@extend_schema(methods=["GET"], responses=OpenApiTypes.OBJECT)
@extend_schema(methods=["POST"], request=OpenApiTypes.OBJECT, responses=OpenApiTypes.OBJECT)
@api_view(["GET", "POST"])
@permission_classes([section("finance")])
def commissions(request):
    """Taux par défaut et par métier. POST : default_commission_percent, trade_<id>."""
    if request.method == "POST":

        def rate(key):
            raw = str(request.data.get(key, "")).strip().rstrip("%").strip()
            if raw == "":
                return None
            if not raw.isdecimal() or not raw.isascii() or int(raw) > 50:
                raise ValidationError({key: "Un taux entier de 0 à 50 %."})
            return int(raw)

        default = rate("default_commission_percent")
        if default is None:
            raise ValidationError({"default_commission_percent": "Indiquez le taux par défaut."})
        per_trade = {
            int(key.removeprefix("trade_")): rate(key)
            for key in request.data
            if key.startswith("trade_") and key.removeprefix("trade_").isdecimal()
        }
        services.update_commissions(request.user, default, per_trade)
    default = PlatformSettings.load().default_commission_percent
    return Response(
        {
            "default_commission_percent": default,
            "trades": [
                {
                    "id": t.pk,
                    "name": t.name,
                    "icon": t.icon,
                    "is_active": t.is_active,
                    "commission_percent": t.commission_percent,
                    "effective": t.commission_percent
                    if t.commission_percent is not None
                    else default,
                }
                for t in Trade.objects.order_by("position", "name")
            ],
        }
    )


TRANSACTION_SORTS = {"recent": ("-updated_at",), "amount": ("-price", "-updated_at")}


@extend_schema(
    parameters=[
        OpenApiParameter("days", int),
        OpenApiParameter("trade", str),
        OpenApiParameter("pro", int),
        OpenApiParameter("coupon", str, description="code, ou * pour « avec un code »"),
        OpenApiParameter("status", str, enum=["booked", "done"]),
        OpenApiParameter("sort", str, enum=["recent", "amount"]),
    ]
)
class TransactionConsoleViewSet(ConsoleViewSet):
    """Missions réservées et leurs montants : prix, remise, commission, ce que paie le client."""

    console_section = "finance"
    serializer_class = s.TransactionSerializer

    def get_queryset(self):
        qs = finance.missions()
        days = self.param("days")
        qs = finance.period_filter(
            qs,
            int(days) if days.isdecimal() and days.isascii() and len(days) <= 4 else None,
            self.param("trade"),
            self.param("pro"),
            self.param("coupon"),
        )
        if (status := self.param("status")) == "booked":
            # En cours : y compris une annulation demandée, pas encore confirmée.
            qs = qs.filter(status__in=[S.BOOKED, S.CANCELLING])
        elif status == "done":
            qs = qs.filter(status=status)
        return self.sort(qs, TRANSACTION_SORTS, TRANSACTION_SORTS["recent"])

    def list(self, request):
        qs = self.get_queryset()
        page = self.paginate_queryset(qs)
        response = self.get_paginated_response(s.TransactionSerializer(page, many=True).data)
        response.data["totals"] = finance.totals(qs)
        return response

    @extend_schema(responses={(200, "text/csv"): OpenApiTypes.STR})
    @action(detail=False, methods=["get"])
    def export(self, request):
        rows = (
            [
                r.pk,
                timezone.localtime(r.updated_at).strftime("%d/%m/%Y"),
                r.get_status_display(),
                r.title,
                r.trade.name,
                r.zone.name,
                r.client.get_full_name(),
                r.pro.get_full_name() if r.pro else "",
                r.price,
                r.discount,
                r.coupon.code if r.coupon_id else "",
                r.commission_rate,
                r.commission,
                r.price - r.discount,
                r.commission - r.discount,
            ]
            for r in self.get_queryset()
        )
        header = [
            "N°",
            "Mise à jour",
            "Statut",
            "Demande",
            "Métier",
            "Quartier",
            "Client",
            "Pro",
            "Devis (F CFA)",
            "Remise (F CFA)",
            "Code promo",
            "Commission (%)",
            "Commission (F CFA)",
            "Payé par le client (F CFA)",
            "Net Jeflink (F CFA)",
        ]
        return _csv("jeflink-transactions.csv", header, rows)


class BalanceConsoleViewSet(ConsoleViewSet):
    """Soldes des pros : commission due moins remises, corrigée des règlements enregistrés."""

    console_section = "finance"
    pagination_class = None
    serializer_class = s.SettlementSerializer

    def _row(self, row) -> dict:
        profile = row["pro"]
        return {
            "pro": {
                "id": profile.user_id,
                "name": profile.user.get_full_name() or profile.user.email,
                "phone": profile.user.phone,
                "photo": profile.photo or profile.user.photo,
            },
            **{k: row[k] for k in ("missions_done", "due", "settled", "balance")},
        }

    def list(self, request):
        rows = [self._row(r) for r in finance.balances()]
        owed = sum(r["balance"] for r in rows if r["balance"] > 0)
        to_pay = -sum(r["balance"] for r in rows if r["balance"] < 0)
        return Response({"results": rows, "totals": {"owed_by_pros": owed, "owed_to_pros": to_pay}})

    def retrieve(self, request, pk=None):
        profile = get_object_or_404(ProProfile.objects.select_related("user"), user_id=pk)
        missions = (
            finance.missions().filter(pro=profile.user, status=S.DONE).order_by("-updated_at")
        )
        return Response(
            {
                **self._row({"pro": profile, **finance.pro_balance(profile.user)}),
                "missions": s.TransactionSerializer(missions[:30], many=True).data,
                "settlements": s.SettlementSerializer(
                    ProSettlement.objects.filter(pro=profile.user).select_related("recorded_by"),
                    many=True,
                ).data,
            }
        )

    @extend_schema(request=s.SettlementInputSerializer, responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["post"])
    def settle(self, request, pk=None):
        profile = get_object_or_404(ProProfile.objects.select_related("user"), user_id=pk)
        data = s.SettlementInputSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        services.add_settlement(request.user, profile.user, data.validated_data)
        return self.retrieve(request, pk)


@extend_schema(
    parameters=[OpenApiParameter("month", str, description="AAAA-MM")],
    responses=OpenApiTypes.OBJECT,
)
@api_view(["GET"])
@permission_classes([section("finance")])
def reports(request):
    """Six derniers mois (missions terminées) et détail par métier du mois choisi."""
    months = finance.monthly(6)
    chosen = request.query_params.get("month", "") or months[0]["month"]
    try:
        year, month = (int(x) for x in chosen.split("-"))
        trades = finance.by_trade(year, month)
    except (ValueError, TypeError):
        raise ValidationError({"month": "Mois au format AAAA-MM."}) from None
    return Response({"months": months, "month": chosen, "by_trade": trades})


@extend_schema(responses={(200, "text/csv"): OpenApiTypes.STR})
@api_view(["GET"])
@permission_classes([section("finance")])
def reports_export(request):
    rows = (
        [
            m["month"],
            m["requests"],
            m["booked"],
            m["count"],
            m["volume"],
            m["discount"],
            m["commission"],
            m["net"],
            m["coupons_used"],
        ]
        for m in finance.monthly(12)
    )
    header = [
        "Mois",
        "Demandes publiées",
        "Réservées",
        "Missions terminées",
        "Volume (F CFA)",
        "Remises (F CFA)",
        "Commissions (F CFA)",
        "Net Jeflink (F CFA)",
        "Codes promo utilisés",
    ]
    return _csv("jeflink-rapport-mensuel.csv", header, rows)


# --- Jef -----------------------------------------------------------------------------------------


class JefConsoleViewSet(ConsoleViewSet):
    """Échanges avec Jef : ce que les clients ont écrit, les questions posées, les fiches."""

    console_section = "operations"
    serializer_class = s.JefSessionSerializer

    def get_queryset(self):
        qs = JefSession.objects.select_related("client", "trade", "request")
        if (mode := self.param("mode")) in JefSession.Mode.values:
            qs = qs.filter(mode=mode)
        if (published := self.param("published")) in ("0", "1"):
            qs = qs.filter(request__isnull=published == "0")
        return qs

    def list(self, request):
        response = self.paginated(self.get_queryset(), s.JefSessionSerializer)
        recent = JefSession.objects.filter(created_at__gte=timezone.now() - timedelta(days=30))
        counts = recent.aggregate(
            sessions=Count("id"),
            briefs=Count("id", filter=Q(brief__isnull=False)),
            published=Count("id", filter=Q(request__isnull=False)),
            ai=Count("id", filter=Q(mode=JefSession.Mode.AI)),
        )
        requests = ServiceRequest.objects.filter(
            created_at__gte=timezone.now() - timedelta(days=30)
        ).count()
        response.data["status"] = {
            "enabled": PlatformSettings.load().jef_enabled,
            "ai": jef_ai.enabled(),  # clé présente : on ne renvoie jamais sa valeur
            "model": settings.JEF_MODEL if jef_ai.enabled() else "",
            "daily_limit": settings.JEF_DAILY_LIMIT,
        }
        response.data["stats"] = {**counts, "requests": requests}
        return response
