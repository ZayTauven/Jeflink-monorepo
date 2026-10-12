"""API de la console d'administration : réservée à l'équipe Jeflink (comptes ``is_staff``).

Lecture : listes filtrées et paginées (20 par page), fiches détaillées.
Écriture : actions explicites (vérifier, suspendre, masquer…) qui passent par ``services`` et sont
journalisées. Aucune modification libre d'un enregistrement.
"""

from datetime import timedelta

from django.db.models import Count, IntegerField, Max, OuterRef, Q, Subquery, Sum, Value
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

from jeflink.accounts.models import ContactMessage, ProProfile, User
from jeflink.catalog.models import Trade, Zone
from jeflink.jobs.models import Dispute, Quote, Review, ServiceRequest

from . import serializers as s
from . import services, stats
from .models import AuditLog, PlatformSettings
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


@extend_schema(
    parameters=[
        OpenApiParameter("status", str, enum=[v for v in S.values]),
        OpenApiParameter("trade", str, description="slug du métier"),
        OpenApiParameter("zone", str, description="slug du quartier"),
        OpenApiParameter("q", str, description="n°, titre, client ou pro"),
        OpenApiParameter("urgent", bool),
        OpenApiParameter("stale", bool, description="ouvertes depuis 24 h sans devis"),
        OpenApiParameter("dispute", bool, description="avec un litige en cours"),
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
        return self.paginated(qs.order_by("-created_at"), s.RequestRowSerializer, facets)

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


@extend_schema(
    parameters=[
        OpenApiParameter("status", str, enum=["pending", "verified", "suspended"]),
        OpenApiParameter("trade", str),
        OpenApiParameter("q", str),
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
            qs = qs.filter(is_verified=False, user__is_active=True).order_by("user__date_joined")
        elif status == "verified":
            qs = qs.filter(is_verified=True, user__is_active=True)
        elif status == "suspended":
            qs = qs.filter(user__is_active=False)
        if trade := self.param("trade"):
            qs = qs.filter(trades__slug=trade)
        if q := self.param("q"):
            qs = qs.filter(search_people("user__", q) | Q(headline__icontains=q))
        if status != "pending":
            qs = qs.order_by("user__first_name", "user__last_name")
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
        return Zone.objects.annotate(
            n_pros=Count(
                "pros", filter=Q(pros__is_verified=True, pros__user__is_active=True), distinct=True
            ),
            n_recent=Count(
                "servicerequest",
                filter=Q(servicerequest__created_at__gte=_recent()),
                distinct=True,
            ),
        ).order_by("city", "position", "name")

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
