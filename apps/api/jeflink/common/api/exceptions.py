"""Réponses d'erreur homogènes : ``{"code": "...", ...}``, sans écho de la saisie."""

from typing import Any

from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.http import Http404
from rest_framework import exceptions, status
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

from jeflink.common.errors import DomainError


def _codes(detail: Any) -> Any:
    """Réduit un détail DRF à ses seuls codes (les messages peuvent recopier la saisie)."""
    if isinstance(detail, dict):
        return {key: _codes(value) for key, value in detail.items()}
    if isinstance(detail, list):
        return [_codes(item) for item in detail]
    return getattr(detail, "code", "invalid")


def exception_handler(exc: Exception, context: dict[str, Any]) -> Response | None:
    if isinstance(exc, DomainError):
        return Response({"code": exc.code, **exc.extra}, status=exc.status_code)
    if isinstance(exc, Http404):
        return Response({"code": "not_found"}, status=status.HTTP_404_NOT_FOUND)
    if isinstance(exc, DjangoPermissionDenied):
        exc = exceptions.PermissionDenied()

    response = drf_exception_handler(exc, context)
    if response is None:
        return None
    if isinstance(exc, exceptions.ValidationError):
        response.data = {"code": "invalid", "fields": _codes(exc.detail)}
    elif isinstance(exc, exceptions.APIException):
        code = exc.get_codes()
        response.data = {"code": code if isinstance(code, str) else "error"}
        wait = getattr(exc, "wait", None)
        if wait is not None:
            response.data["retry_after"] = int(wait)
    return response
