"""Identifiant de requête, propagé aux journaux et aux ``AuditEvent``."""

import re
import uuid
from collections.abc import Callable
from contextvars import ContextVar

from django.http import HttpRequest, HttpResponse

_request_id: ContextVar[str] = ContextVar("request_id", default="")
_VALID = re.compile(r"^[A-Za-z0-9-]{8,64}$")


def current_request_id() -> str:
    return _request_id.get()


class RequestIdMiddleware:
    """Reprend ``X-Request-Id`` s'il est bien formé (BFF, proxy), sinon en génère un."""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        incoming = request.headers.get("X-Request-Id", "")
        request_id = incoming if _VALID.match(incoming) else uuid.uuid4().hex
        token = _request_id.set(request_id)
        try:
            response = self.get_response(request)
        finally:
            _request_id.reset(token)
        response["X-Request-Id"] = request_id
        return response
