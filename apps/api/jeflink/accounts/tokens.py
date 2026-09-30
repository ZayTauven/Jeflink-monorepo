"""Jetons d'accès JWT (ADR 0007) : HS256, clé choisie par ``kid`` parmi celles en rotation.

La première clé de ``JWT_SIGNING_KEYS`` signe ; toutes vérifient (rotation sans coupure).
Aucun rôle dans le jeton : les rôles sont relus en base.
"""

import uuid
from datetime import datetime
from typing import Any

import jwt
from django.conf import settings

from jeflink.common.errors import DomainError

ALGORITHM = "HS256"
ISSUER = "jeflink"
AUDIENCE = "jeflink-api"
REQUIRED_CLAIMS = ["exp", "iat", "sub", "sid", "auth_time", "iss", "aud"]


def _timestamp(value: datetime | None) -> int | None:
    return int(value.timestamp()) if value else None


def encode_access(
    *,
    user_public_id: uuid.UUID,
    session_public_id: uuid.UUID,
    app: str,
    auth_time: datetime,
    mfa_at: datetime | None,
    restricted: bool,
    issued_at: datetime,
    expires_at: datetime,
) -> str:
    kid, key = next(iter(settings.JWT_SIGNING_KEYS.items()))
    claims = {
        "iss": ISSUER,
        "aud": AUDIENCE,
        "sub": str(user_public_id),
        "sid": str(session_public_id),
        "app": app,
        "auth_time": _timestamp(auth_time),
        "mfa": mfa_at is not None,
        "mfa_at": _timestamp(mfa_at),
        "restricted": restricted,
        "iat": _timestamp(issued_at),
        "exp": _timestamp(expires_at),
        "jti": uuid.uuid4().hex,
    }
    return jwt.encode(claims, key, algorithm=ALGORITHM, headers={"kid": kid})


def decode_access(token: str) -> dict[str, Any]:
    """Vérifie signature, ``kid``, expiration, émetteur et audience. Lève ``token_*``."""
    try:
        kid = jwt.get_unverified_header(token).get("kid")
    except jwt.PyJWTError as exc:
        raise DomainError("token_invalid", status=401) from exc
    key = settings.JWT_SIGNING_KEYS.get(kid) if isinstance(kid, str) else None
    if key is None:
        raise DomainError("token_invalid", status=401)
    try:
        return jwt.decode(
            token,
            key,
            algorithms=[ALGORITHM],
            audience=AUDIENCE,
            issuer=ISSUER,
            options={"require": REQUIRED_CLAIMS},
        )
    except jwt.ExpiredSignatureError as exc:
        raise DomainError("token_expired", status=401) from exc
    except jwt.PyJWTError as exc:
        raise DomainError("token_invalid", status=401) from exc
