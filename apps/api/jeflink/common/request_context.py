"""Identifiant de requête, propagé aux journaux et aux ``AuditEvent``."""

import hmac
import re
import uuid
from collections.abc import Callable
from contextvars import ContextVar

from django.conf import settings
from django.http import HttpRequest, HttpResponse

_request_id: ContextVar[str] = ContextVar("request_id", default="")
_VALID = re.compile(r"^[A-Za-z0-9-]{8,64}$")
BFF_SECRET_HEADER = "X-Jeflink-Bff"  # noqa: S105 (nom d'en-tête, pas un secret)


def current_request_id() -> str:
    return _request_id.get()


def is_trusted_bff(request: HttpRequest) -> bool:
    """La requête porte un secret BFF valide (deux valeurs acceptées pendant une rotation)."""
    presented = request.headers.get(BFF_SECRET_HEADER, "").encode()
    return bool(presented) and any(
        hmac.compare_digest(presented, secret.encode()) for secret in settings.BFF_SHARED_SECRETS
    )


class RequestIdMiddleware:
    """Génère l'identifiant ; ne reprend ``X-Request-Id`` que depuis le BFF authentifié (M8)."""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        incoming = request.headers.get("X-Request-Id", "")
        trusted = _VALID.match(incoming) and is_trusted_bff(request)
        request_id = incoming if trusted else uuid.uuid4().hex
        token = _request_id.set(request_id)
        try:
            response = self.get_response(request)
        finally:
            _request_id.reset(token)
        response["X-Request-Id"] = request_id
        return response
