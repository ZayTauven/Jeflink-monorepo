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
from functools import cache

from django.conf import settings
from django.db.models import F
from django.utils import timezone

from jeflink.common.alerts import alert_once
from jeflink.common.errors import DomainError
from jeflink.trust.models import AuditEvent
from jeflink.trust.services import audit

from .models import DeviceSession, ReviewAccess, User
from .phone import normalize_phone

REVIEW_APPS = frozenset({"client", "pro"})
# Au-delà, le code est invalidé : il faut relancer la commande (revue sécurité tâche 17, I2).
MAX_CODE_FAILURES = 20


def review_until() -> datetime | None:
    """Fin de la fenêtre de revue (``OTP_REVIEW_ENABLED_UNTIL``, ISO 8601), ou None."""
    raw = settings.OTP_REVIEW_ENABLED_UNTIL
    if not raw:
        return None
    value = datetime.fromisoformat(raw)
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def review_phones() -> frozenset[str]:
    """Numéros de revue normalisés. Une entrée invalide est ignorée (et alertée) : elle ne doit
    jamais couper les connexions ; le check E103 la refuse au déploiement (M4)."""
    return _normalized(tuple(settings.OTP_REVIEW_ACCOUNTS))


@cache
def _normalized(raw_numbers: tuple[str, ...]) -> frozenset[str]:
    phones = set()
    for index, raw in enumerate(raw_numbers):
        try:
            phones.add(normalize_phone(raw))
        except DomainError:
            alert_once(f"review_phone_invalid:{index}", 3600, "review_phone_invalid", index=index)
    return frozenset(phones)


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
    """Comparaison en temps constant. Un échec est alerté dès le premier (anormal : seule
    l'équipe de revue connaît le code) et compté ; au-delà du seuil, le code est invalidé."""
    access = ReviewAccess.objects.filter(user=user).first()
    usable = access is not None and bool(access.code_hash)
    stored = access.code_hash if usable else hashlib.sha256(secrets.token_bytes(8)).hexdigest()
    if hmac.compare_digest(_hash(user, code), stored) and usable:
        return True
    if access is not None:
        ReviewAccess.objects.filter(pk=access.pk).update(failed_attempts=F("failed_attempts") + 1)
        ReviewAccess.objects.filter(pk=access.pk, failed_attempts__gte=MAX_CODE_FAILURES).exclude(
            code_hash=""
        ).update(code_hash="")
    alert_once(f"review_code_failed:{user.public_id}", 600, "review_code_failed")
    return False


def end_review_sessions(user: User) -> int:
    """Coupe les sessions du compte de revue (rotation du code, fin de la fenêtre) (I1)."""
    from .sessions import revoke_all_sessions

    return revoke_all_sessions(user=user, reason=DeviceSession.RevokedReason.REVIEW_ENDED)


def close_ended_reviews() -> int:
    """Tâche quotidienne : fenêtre fermée → plus aucune session sur un compte de revue."""
    if review_window_open():
        return 0
    revoked = 0
    for user in User.objects.filter(
        is_review_account=True,
        device_sessions__revoked_at__isnull=True,
    ).distinct():
        revoked += end_review_sessions(user)
    return revoked


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
        defaults={
            "code_hash": _hash(user, code),
            "rotated_by_operator": operator[:64],
            "failed_attempts": 0,
        },
    )
    # Les sessions ouvertes avec l'ancien code (soumission précédente) sont coupées (I1).
    end_review_sessions(user)
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
