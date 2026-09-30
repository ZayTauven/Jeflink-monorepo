"""Compte de revue des stores Apple et Google (spec 001, S17 ; tâche 17).

Les équipes de revue doivent pouvoir se connecter sans recevoir de SMS. Le compte est encadré :
- numéro d'une SIM détenue par Jeflink, listé dans ``OTP_REVIEW_ACCOUNTS`` ;
- compte **marqué** ``is_review_account``, créé par la commande ``create_review_account`` (deux
  Admin, auditée), jamais par une connexion : un numéro de revue ne crée pas de compte ;
- code aléatoire changé à chaque soumission, stocké en HMAC, comparé en temps constant ;
- actif seulement jusqu'à ``OTP_REVIEW_ENABLED_UNTIL`` et pour les apps ``client`` et ``pro`` ;
- chaque usage est audité et alerté.

Hors de ces bornes, le numéro se comporte comme n'importe quel autre (SMS vers la SIM Jeflink),
et le compte marqué ne peut pas se connecter.
"""

import hashlib
import hmac
import secrets
from datetime import UTC, datetime

from django.conf import settings
from django.utils import timezone

from jeflink.common.alerts import alert_once
from jeflink.common.errors import DomainError
from jeflink.trust.models import AuditEvent
from jeflink.trust.services import audit

from .models import ReviewAccess, User
from .phone import normalize_phone

REVIEW_APPS = frozenset({"client", "pro"})


def review_until() -> datetime | None:
    """Fin de la fenêtre de revue (``OTP_REVIEW_ENABLED_UNTIL``, ISO 8601), ou None."""
    raw = settings.OTP_REVIEW_ENABLED_UNTIL
    if not raw:
        return None
    value = datetime.fromisoformat(raw)
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def review_phones() -> frozenset[str]:
    return frozenset(normalize_phone(raw) for raw in settings.OTP_REVIEW_ACCOUNTS)


def is_review_phone(phone: str) -> bool:
    return phone in review_phones()


def review_window_open() -> bool:
    until = review_until()
    return until is not None and timezone.now() < until


def review_user_for(phone: str, app: str) -> User | None:
    """Compte de revue utilisable pour ce numéro et cette app, maintenant ; sinon None."""
    if app not in REVIEW_APPS or not is_review_phone(phone) or not review_window_open():
        return None
    return User.objects.filter(
        phone=phone, is_review_account=True, is_active=True, deleted_at__isnull=True
    ).first()


def _hash(user: User, code: str) -> str:
    key = settings.OTP_HMAC_KEY.encode()
    message = f"review|{user.public_id}|{code}".encode()
    return hmac.new(key, message, hashlib.sha256).hexdigest()


def review_code_matches(user: User, code: str) -> bool:
    access = ReviewAccess.objects.filter(user=user).first()
    stored = access.code_hash if access else hashlib.sha256(secrets.token_bytes(8)).hexdigest()
    return hmac.compare_digest(_hash(user, code), stored) and access is not None


def record_use(user: User, *, app: str, purpose: str, challenge_public_id) -> None:
    """Chaque usage est audité et alerté (une alerte par challenge)."""
    audit(
        action="accounts.review_account.used",
        actor=user,
        actor_kind=AuditEvent.ActorKind.USER,
        target=user,
        metadata={"app": app, "purpose": purpose},
    )
    alert_once(
        f"review_used:{challenge_public_id}", 3600, "review_account_used", app=app, purpose=purpose
    )


def rotate_code(*, user: User, operator: str, second_operator: str, reason_code: str) -> str:
    """Nouveau code (6 chiffres) pour une soumission ; l'ancien cesse de valoir. Audité."""
    if not user.is_review_account:
        raise DomainError("not_review_account")
    code = f"{secrets.randbelow(10**6):06d}"
    ReviewAccess.objects.update_or_create(
        user=user,
        defaults={"code_hash": _hash(user, code), "rotated_by_operator": operator[:64]},
    )
    audit(
        action="accounts.review_account.code_rotated",
        actor_kind=AuditEvent.ActorKind.OPS,
        target=user,
        metadata={
            "operator": operator,
            "second_operator": second_operator,
            "reason_code": reason_code,
        },
    )
    return code
