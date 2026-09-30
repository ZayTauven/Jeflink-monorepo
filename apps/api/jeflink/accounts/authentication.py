"""Authentification de l'API : Bearer JWT seulement (ADR 0007). Ni session, ni CSRF, ni CORS.

À chaque requête : signature et ``kid`` valides, session active (cache 60 s, repli en base),
compte actif et non technique. L'état « restreint » (compte dormant) est relu côté serveur.
"""

from typing import Any

from rest_framework.authentication import BaseAuthentication, get_authorization_header
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.request import Request

from jeflink.common.errors import DomainError

from .models import User
from .sessions import session_state, touch_session
from .tokens import decode_access


class SessionJWTAuthentication(BaseAuthentication):
    keyword = b"bearer"

    def authenticate(self, request: Request) -> tuple[User, dict[str, Any]] | None:
        header = get_authorization_header(request).split()
        if not header or header[0].lower() != self.keyword:
            return None
        if len(header) != 2:
            raise AuthenticationFailed(code="token_invalid")
        try:
            claims = decode_access(header[1].decode("ascii", errors="replace"))
        except DomainError as exc:
            raise AuthenticationFailed(code=exc.code) from exc

        state = session_state(claims["sid"])
        if state is None:
            raise AuthenticationFailed(code="session_revoked")
        user = User.objects.filter(public_id=claims["sub"]).first()
        if (
            user is None
            or not user.is_active
            or user.deleted_at is not None
            or user.is_staff
            or user.is_superuser
        ):
            raise AuthenticationFailed(code="account_disabled")
        # La restriction vient de la base (via le cache), pas du jeton : une levée par l'Ops
        # prend effet sans attendre l'expiration de l'accès.
        claims["restricted"] = state == "restricted"
        touch_session(claims["sid"])
        return user, claims

    def authenticate_header(self, request: Request) -> str:
        return 'Bearer realm="api"'
