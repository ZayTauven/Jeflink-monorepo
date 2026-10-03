"""Socle des endpoints publics de données de référence (spec 002, ADR 0009).

Lecture seule, sans authentification, réponses légères et cacheables : ``Cache-Control`` public,
``ETag`` et 304. Un appel qui porte un jeton reste ``private, no-store`` (``NoStoreMiddleware``) :
les fronts appellent ces endpoints sans jeton.
"""

import hashlib
import json
from typing import Any

from django.conf import settings
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

PUBLIC_CACHE_CONTROL = "public, max-age=300, stale-while-revalidate=86400"


class LocalizedTextSerializer(serializers.Serializer):
    """Libellé traduisible : le front choisit la langue et retombe sur ``fr`` (ADR 0009)."""

    fr = serializers.CharField()
    wo = serializers.CharField(allow_null=True)

    class Meta:
        ref_name = "LocalizedText"


@extend_schema_field(LocalizedTextSerializer)
class LocalizedTextField(serializers.Field):
    """Lit ``<base>_fr`` et ``<base>_wo`` ; un ``wo`` vide sort en ``null``.

    Avec ``optional=True``, un ``fr`` vide fait sortir tout le champ en ``null``.
    """

    def __init__(self, base: str, *, optional: bool = False, **kwargs: Any) -> None:
        self.base = base
        self.optional = optional
        kwargs.update(source="*", read_only=True, allow_null=optional)
        super().__init__(**kwargs)

    def to_representation(self, instance: Any) -> dict[str, str | None] | None:
        fr = getattr(instance, f"{self.base}_fr")
        if not fr and self.optional:
            return None
        return {"fr": fr, "wo": getattr(instance, f"{self.base}_wo") or None}


def _etag(data: Any) -> str:
    body = json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)
    return '"' + hashlib.sha256(body.encode()).hexdigest()[:32] + '"'


def _matches(header: str, etag: str) -> bool:
    candidates = {tag.strip().removeprefix("W/") for tag in header.split(",")}
    return "*" in candidates or etag in candidates


class PublicReferenceView(APIView):
    """Vue publique de données de référence : ``GET`` seulement, limite par IP ``catalog_read``."""

    permission_classes = [AllowAny]
    authentication_classes = []
    rate_limit_scope = "catalog_read"
    http_method_names = ["get", "head", "options"]

    @staticmethod
    def list_limit() -> int:
        return settings.REFERENCE_LIST_MAX

    def cached_response(self, request: Request, data: Any) -> Response:
        etag = _etag(data)
        if _matches(request.headers.get("If-None-Match", ""), etag):
            response = Response(status=304)
        else:
            response = Response(data)
        response["ETag"] = etag
        response["Cache-Control"] = PUBLIC_CACHE_CONTROL
        return response
