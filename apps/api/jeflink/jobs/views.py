from django.db.models import Q
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from jeflink.jef import services as jef_services

from . import services
from .models import ServiceRequest
from .serializers import (
    AcceptSerializer,
    CancelSerializer,
    DisputeCreateSerializer,
    QuoteCreateSerializer,
    QuoteSerializer,
    RequestCreateSerializer,
    RequestSerializer,
    ReviewCreateSerializer,
    ReviewSerializer,
)


class RequestViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    viewsets.GenericViewSet,
):
    """Demandes. Un client voit les siennes ; un pro voit celles de ses métiers et ses missions."""

    serializer_class = RequestSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):  # génération du schéma OpenAPI
            return ServiceRequest.objects.none()
        user = self.request.user
        qs = services.visible_requests(user)
        if self.action == "list" and user.is_pro:
            scope = self.request.query_params.get("scope", "mine")
            if scope == "open":
                qs = services.open_requests_for_pro(user)
            else:
                qs = ServiceRequest.objects.filter(Q(pro=user) | Q(quotes__pro=user))
        if status_filter := self.request.query_params.get("status"):
            qs = qs.filter(status=status_filter)
        return (
            qs.select_related("trade", "zone", "client", "pro", "review", "jef_session")
            .prefetch_related("events")
            .distinct()
        )

    @extend_schema(
        parameters=[
            OpenApiParameter("scope", str, enum=["mine", "open"], description="pros uniquement"),
            OpenApiParameter("status", str, enum=[s.value for s in ServiceRequest.Status]),
        ]
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(request=RequestCreateSerializer, responses={201: RequestSerializer})
    def create(self, request, *args, **kwargs):
        serializer = RequestCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        jef_session = data.pop("jef_session", None)
        req = services.create_request(request.user, **data)
        if jef_session:
            jef_services.attach(request.user, req, jef_session)
        return Response(self._read(req), status=status.HTTP_201_CREATED)

    @extend_schema(request=QuoteCreateSerializer, responses={201: QuoteSerializer})
    @action(detail=True, methods=["post"])
    def quotes(self, request, pk=None):
        serializer = QuoteCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        quote = services.submit_quote(request.user, self.get_object(), **serializer.validated_data)
        return Response(
            QuoteSerializer(quote, context=self.get_serializer_context()).data,
            status=status.HTTP_201_CREATED,
        )

    @extend_schema(request=AcceptSerializer, responses=RequestSerializer)
    @action(detail=True, methods=["post"])
    def accept(self, request, pk=None):
        serializer = AcceptSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        req = services.accept_quote(
            request.user,
            self.get_object(),
            serializer.validated_data["quote_id"],
            serializer.validated_data["coupon"],
        )
        return Response(self._read(req))

    @extend_schema(request=None, responses=RequestSerializer)
    @action(detail=True, methods=["post"])
    def complete(self, request, pk=None):
        return Response(self._read(services.complete(request.user, self.get_object())))

    @extend_schema(request=CancelSerializer, responses=RequestSerializer)
    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        """Le client annule avec un motif ; mission réservée : en attente du rappel du support."""
        serializer = CancelSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        req = services.cancel(request.user, self.get_object(), **serializer.validated_data)
        return Response(self._read(req))

    @extend_schema(request=ReviewCreateSerializer, responses={201: ReviewSerializer})
    @action(detail=True, methods=["post"])
    def review(self, request, pk=None):
        serializer = ReviewCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        review = services.leave_review(request.user, self.get_object(), **serializer.validated_data)
        return Response(ReviewSerializer(review).data, status=status.HTTP_201_CREATED)

    @extend_schema(request=DisputeCreateSerializer, responses={201: RequestSerializer})
    @action(detail=True, methods=["post"])
    def report(self, request, pk=None):
        """Le client ou le pro signale un problème sur la mission : un litige s'ouvre."""
        if request.user.is_staff:
            # L'équipe ouvre un litige depuis la console, qui le journalise.
            raise PermissionDenied("Passez par la console pour ouvrir un litige.")
        serializer = DisputeCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        req = self.get_object()
        services.open_dispute(request.user, req, **serializer.validated_data)
        return Response(self._read(req), status=status.HTTP_201_CREATED)

    def _read(self, req):
        req = ServiceRequest.objects.get(pk=req.pk)
        return RequestSerializer(req, context=self.get_serializer_context()).data
