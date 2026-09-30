"""Sessions d'appareil : création, rotation du refresh avec grâce, révocation (ADR 0007).

Règles clés :
- le refresh est opaque (``jfr_`` + 32 octets aléatoires), stocké en SHA-256, tourné à
  chaque usage ;
- **grâce** : l'ancien refresh est accepté une seule fois par rotation, 24 h au plus. Il émet un
  nouveau refresh et retire le courant : si le vrai client présente ensuite ce courant retiré,
  la réutilisation est détectée et la session révoquée ;
- toute autre présentation d'un refresh retiré est une **réutilisation** : révocation + audit ;
- la politique de durée est figée à la création ; si elle change (rôle ops accordé ou retiré),
  la session est révoquée au refresh suivant ;
- chaque requête vérifie que la session est active (cache Redis 60 s, repli en base). Une
  révocation pose une pierre tombale dans le cache : aucun lecteur concurrent ne peut y
  réinscrire « active ».
"""

import contextlib
import hashlib
import re
import secrets
import unicodedata
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

import redis
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from jeflink.common.errors import DomainError
from jeflink.common.pii import contains_pii
from jeflink.common.ratelimit import client as auth_redis
from jeflink.trust.models import AuditEvent
from jeflink.trust.services import audit

from .models import DeviceSession, RetiredRefreshToken, Role, TotpDevice, User
from .selectors import has_role
from .tokens import encode_access

REFRESH_PREFIX = "jfr_"
SESSION_CACHE_TTL = 60
_TOMBSTONE = b"x"
# Au moins 128 bits aléatoires côté app (UUID v4 = 36 caractères, 22 en base64url).
_INSTALL_ID = re.compile(r"^[A-Za-z0-9_-]{22,64}$")
# Révocations décidées par le système : jamais attribuées à l'utilisateur dans l'audit (M4).
_SYSTEM_REASONS = frozenset(
    {
        DeviceSession.RevokedReason.REUSE_DETECTED,
        DeviceSession.RevokedReason.LIMIT,
        DeviceSession.RevokedReason.REPLACED,
        DeviceSession.RevokedReason.OPS_ROLE_CHANGED,
        DeviceSession.RevokedReason.ACCOUNT_DISABLED,
        DeviceSession.RevokedReason.MFA_LOCKED,
        DeviceSession.RevokedReason.MFA_RESET,
    }
)


@dataclass(frozen=True)
class TokenPair:
    access: str
    refresh: str
    access_expires_at: datetime
    session: DeviceSession


@dataclass(frozen=True)
class SessionState:
    restricted: bool
    user_public_id: str


# --- Politique ---------------------------------------------------------------------------


def policy_name(session: DeviceSession) -> str:
    """Console d'un compte ops : politique courte (30 min d'inactivité, 12 h au plus, S25)."""
    if session.app == DeviceSession.App.CONSOLE and has_role(session.user, Role.OPS):
        return "console_ops"
    return session.app


def _policy(name: str) -> dict[str, timedelta]:
    return {key: timedelta(seconds=value) for key, value in settings.SESSION_POLICIES[name].items()}


# --- Outils -------------------------------------------------------------------------------


def hash_refresh(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _new_refresh() -> tuple[str, str]:
    token = REFRESH_PREFIX + secrets.token_urlsafe(32)
    return token, hash_refresh(token)


def clean_device_label(raw: str) -> str:
    """Libellé d'appareil (« Samsung A05 ») : court, sans contrôle ni donnée personnelle."""
    label = "".join(
        ch for ch in (raw or "") if unicodedata.category(ch) not in {"Cc", "Cf", "Co", "Cn"}
    )
    label = " ".join(label.split())[:60]
    return "" if contains_pii(label) else label


def clean_install_id(raw: str) -> str:
    return raw if raw and _INSTALL_ID.match(raw) else ""


def new_install_id() -> str:
    """Identifiant d'installation conforme (UUID v4), pour les tests et les outils."""
    return str(uuid.uuid4())


def _cache_key(sid) -> str:
    return f"jf:auth:sid:{sid}"


def _cache_value(session: DeviceSession) -> str:
    return f"{'r' if session.restricted else 'a'}:{session.user.public_id}"


def _cache_fill(session: DeviceSession) -> None:
    """Remplit le cache sans jamais écraser (NX) : une pierre tombale reste en place."""
    with contextlib.suppress(redis.RedisError):
        auth_redis().set(
            _cache_key(session.public_id), _cache_value(session), ex=SESSION_CACHE_TTL, nx=True
        )


def _cache_tombstone(sid) -> None:
    with contextlib.suppress(redis.RedisError):
        auth_redis().set(_cache_key(sid), _TOMBSTONE, ex=SESSION_CACHE_TTL)


def _mfa_at(session: DeviceSession) -> datetime | None:
    """Claim ``mfa`` recalculé à chaque émission : un TOTP réinitialisé ou verrouillé, ou une
    session hors console ops, donne ``mfa = false`` (S1)."""
    if session.policy != "console_ops" or session.mfa_verified_at is None:
        return None
    # Défense en profondeur (revue, M7) : un facteur ré-enrôlé ne revalide pas une session
    # dont le second facteur date d'avant cet enrôlement.
    usable = TotpDevice.objects.filter(
        user=session.user,
        confirmed_at__isnull=False,
        confirmed_at__lte=session.mfa_verified_at,
        locked_at__isnull=True,
    ).exists()
    return session.mfa_verified_at if usable else None


def issue_access(session: DeviceSession, now: datetime) -> tuple[str, datetime]:
    """Jeton d'accès seul, pour la même session (step-up TOTP) : le refresh ne change pas."""
    expires = now + _policy(session.policy)["access"]
    access = encode_access(
        user_public_id=session.user.public_id,
        session_public_id=session.public_id,
        app=session.app,
        auth_time=session.auth_time,
        mfa_at=_mfa_at(session),
        restricted=session.restricted,
        issued_at=now,
        expires_at=expires,
    )
    return access, expires


def _issue(session: DeviceSession, refresh: str, now: datetime) -> TokenPair:
    policy = _policy(session.policy)
    expires = now + policy["access"]
    mfa_at = _mfa_at(session)
    access = encode_access(
        user_public_id=session.user.public_id,
        session_public_id=session.public_id,
        app=session.app,
        auth_time=session.auth_time,
        mfa_at=mfa_at,
        restricted=session.restricted,
        issued_at=now,
        expires_at=expires,
    )
    return TokenPair(access=access, refresh=refresh, access_expires_at=expires, session=session)


def _extend_idle(session: DeviceSession, now: datetime) -> None:
    idle = _policy(session.policy)["idle"]
    session.last_seen_at = now
    session.idle_expires_at = min(now + idle, session.absolute_expires_at)


def account_allowed(user: User) -> bool:
    """Compte autorisé à détenir une session API : actif, non supprimé, non technique (S3)."""
    return (
        user.is_active and user.deleted_at is None and not user.is_staff and not user.is_superuser
    )


# --- Création -------------------------------------------------------------------------------


@transaction.atomic
def create_session(
    *,
    user: User,
    app: str,
    platform: str,
    device_label: str = "",
    install_id: str = "",
    mfa_verified_at: datetime | None = None,
    restricted: bool = False,
) -> TokenPair:
    """Ouvre une session après un OTP réussi. Au plus ``MAX_ACTIVE_SESSIONS`` par compte.

    Un compte marqué dormant n'obtient que des sessions restreintes, quel que soit l'appareil.
    """
    now = timezone.now()
    install_id = clean_install_id(install_id)
    user = User.objects.select_for_update(no_key=True).get(pk=user.pk)
    if not account_allowed(user):
        raise DomainError("account_not_allowed", status=403)
    if restricted and user.dormant_restricted_since is None:
        user.dormant_restricted_since = now
        user.save(update_fields=["dormant_restricted_since", "updated_at"])
    restricted = restricted or user.dormant_restricted_since is not None

    active = DeviceSession.objects.filter(
        user=user, revoked_at__isnull=True, idle_expires_at__gt=now, absolute_expires_at__gt=now
    )
    if install_id:
        for previous in active.filter(app=app, install_id=install_id):
            revoke_session(previous, reason=DeviceSession.RevokedReason.REPLACED)
    surplus = active.count() - (settings.MAX_ACTIVE_SESSIONS - 1)
    for oldest in active.order_by("last_seen_at")[: max(surplus, 0)]:
        revoke_session(oldest, reason=DeviceSession.RevokedReason.LIMIT)
        audit(
            action="accounts.session.evicted_limit",
            actor_kind=AuditEvent.ActorKind.SYSTEM,
            target=user,
            metadata={"app": oldest.app},
        )

    refresh, refresh_hash = _new_refresh()
    session = DeviceSession(
        user=user,
        app=app,
        platform=platform,
        device_label=clean_device_label(device_label),
        install_id=install_id,
        refresh_hash=refresh_hash,
        auth_time=now,
        mfa_verified_at=mfa_verified_at,
        restricted=restricted,
        last_seen_at=now,
    )
    session.policy = policy_name(session)
    policy = _policy(session.policy)
    session.absolute_expires_at = now + policy["absolute"]
    session.idle_expires_at = min(now + policy["idle"], session.absolute_expires_at)
    session.save()
    transaction.on_commit(lambda: _cache_fill(session))
    return _issue(session, refresh, now)


# --- Rotation -------------------------------------------------------------------------------


def refresh_session(refresh: str) -> TokenPair:
    """Échange un refresh contre un nouveau couple. Lève ``refresh_invalid`` ou ``session_revoked``.

    Une réutilisation ou un changement de politique révoque la session : la révocation et
    l'audit sont validés avant l'erreur.
    """
    if not refresh or not refresh.startswith(REFRESH_PREFIX):
        raise DomainError("refresh_invalid", status=401)
    presented = hash_refresh(refresh)
    reuse_detected: DeviceSession | None = None

    with transaction.atomic():
        now = timezone.now()
        base = DeviceSession.objects.select_for_update().select_related("user")
        session = base.filter(refresh_hash=presented).first()
        is_current = session is not None
        if session is None:
            session = base.filter(previous_refresh_hash=presented).first()
        if session is None:
            retired = RetiredRefreshToken.objects.filter(refresh_hash=presented).first()
            if retired is None:
                raise DomainError("refresh_invalid", status=401)
            session = base.get(pk=retired.session_id)
            if session.revoked_at is None:
                revoke_session(session, reason=DeviceSession.RevokedReason.REUSE_DETECTED)
                reuse_detected = session
        elif not _usable(session, now):
            raise DomainError("session_revoked", status=401)
        elif policy_name(session) != session.policy:
            # Rôle ops accordé ou retiré depuis la connexion : nouvelle connexion exigée (I2).
            revoke_session(session, reason=DeviceSession.RevokedReason.OPS_ROLE_CHANGED)
        elif is_current:
            return _rotate(session, now, grace=False)
        elif _grace_available(session, now):
            return _rotate(session, now, grace=True)
        else:
            # Ancien refresh présenté alors que la grâce ne s'applique plus : réutilisation.
            revoke_session(session, reason=DeviceSession.RevokedReason.REUSE_DETECTED)
            reuse_detected = session

    if reuse_detected is not None:
        audit(
            action="accounts.session.refresh_reuse_detected",
            actor_kind=AuditEvent.ActorKind.SYSTEM,
            target=reuse_detected.user,
            session_public_id=reuse_detected.public_id,
            metadata={"app": reuse_detected.app},
            durable=True,
        )
    raise DomainError("session_revoked", status=401)


def _usable(session: DeviceSession, now: datetime) -> bool:
    return (
        session.revoked_at is None
        and session.idle_expires_at > now
        and session.absolute_expires_at > now
        and account_allowed(session.user)
    )


def _grace_available(session: DeviceSession, now: datetime) -> bool:
    return (
        session.grace_used_at is None
        and session.rotated_at is not None
        and now - session.rotated_at <= timedelta(seconds=settings.REFRESH_GRACE_SECONDS)
    )


def _rotate(session: DeviceSession, now: datetime, *, grace: bool) -> TokenPair:
    """Nouveau refresh. En grâce : l'ancien reste « précédent » (grâce consommée), le courant
    est retiré ; sinon le courant devient le précédent."""
    refresh, refresh_hash = _new_refresh()
    RetiredRefreshToken.objects.create(session=session, refresh_hash=session.refresh_hash)
    if grace:
        session.grace_used_at = now
    else:
        session.previous_refresh_hash = session.refresh_hash
        session.rotated_at = now
        session.grace_used_at = None
    session.refresh_hash = refresh_hash
    _extend_idle(session, now)
    session.save()
    transaction.on_commit(lambda: _cache_fill(session))
    return _issue(session, refresh, now)


def reissue_session(session: DeviceSession) -> TokenPair:
    """Rejeu de ``otp/verify`` (T1) : nouveaux jetons pour la **même** session, avec rotation.

    Le refresh courant est retiré ; aucune grâce n'est ouverte (le client a perdu la réponse
    précédente, il repart du couple émis ici).
    """
    with transaction.atomic():
        now = timezone.now()
        session = (
            DeviceSession.objects.select_for_update().select_related("user").get(pk=session.pk)
        )
        if not _usable(session, now):
            raise DomainError("session_revoked", status=401)
        refresh, refresh_hash = _new_refresh()
        RetiredRefreshToken.objects.create(session=session, refresh_hash=session.refresh_hash)
        session.refresh_hash = refresh_hash
        _extend_idle(session, now)
        session.save()
        transaction.on_commit(lambda: _cache_fill(session))
        return _issue(session, refresh, now)


# --- Révocation -------------------------------------------------------------------------------


def revoke_session(session: DeviceSession, *, reason: str, actor: User | None = None) -> None:
    if session.revoked_at is not None:
        return
    session.revoked_at = timezone.now()
    session.revoked_reason = reason
    session.save(update_fields=["revoked_at", "revoked_reason", "updated_at"])
    sid = session.public_id
    # Pierre tombale immédiate (effet instantané), puis à nouveau après commit : un lecteur
    # concurrent ne peut plus réinscrire « active » (le remplissage se fait en NX).
    _cache_tombstone(sid)
    transaction.on_commit(lambda: _cache_tombstone(sid))
    if reason in _SYSTEM_REASONS:
        actor, actor_kind = None, AuditEvent.ActorKind.SYSTEM
    elif reason == DeviceSession.RevokedReason.OPS_REVOKED:
        actor_kind = AuditEvent.ActorKind.OPS
    else:
        actor, actor_kind = actor or session.user, AuditEvent.ActorKind.USER
    audit(
        action="accounts.session.revoked",
        actor=actor,
        actor_kind=actor_kind,
        target=session.user,
        session_public_id=session.public_id,
        metadata={"reason": reason, "app": session.app},
    )


@transaction.atomic
def revoke_other_sessions(*, user: User, current_sid, reason: str) -> int:
    sessions = DeviceSession.objects.select_for_update().filter(user=user, revoked_at__isnull=True)
    revoked = 0
    for session in sessions.exclude(public_id=current_sid):
        revoke_session(session, reason=reason, actor=user)
        revoked += 1
    return revoked


@transaction.atomic
def revoke_all_sessions(
    *, user: User, reason: str, actor: User | None = None, app: str | None = None
) -> int:
    sessions = DeviceSession.objects.select_for_update().filter(user=user, revoked_at__isnull=True)
    if app is not None:
        sessions = sessions.filter(app=app)
    revoked = 0
    for session in sessions:
        revoke_session(session, reason=reason, actor=actor)
        revoked += 1
    return revoked


# --- Vérification à chaque requête ---------------------------------------------------------


def session_state(sid) -> SessionState | None:
    """État d'une session active, ou None (révoquée, expirée, inconnue)."""
    with contextlib.suppress(redis.RedisError):
        cached = auth_redis().get(_cache_key(sid))
        if cached == _TOMBSTONE:
            return None
        if cached:
            kind, _, user_public_id = cached.decode().partition(":")
            return SessionState(restricted=kind == "r", user_public_id=user_public_id)
    now = timezone.now()
    session = (
        DeviceSession.objects.select_related("user")
        .filter(
            public_id=sid,
            revoked_at__isnull=True,
            idle_expires_at__gt=now,
            absolute_expires_at__gt=now,
        )
        .first()
    )
    if session is None:
        return None
    _cache_fill(session)
    return SessionState(restricted=session.restricted, user_public_id=str(session.user.public_id))


def touch_session(sid) -> None:
    """Met à jour ``last_seen_at`` au plus toutes les 10 min (sert au compte dormant)."""
    now = timezone.now()
    DeviceSession.objects.filter(
        public_id=sid, last_seen_at__lt=now - timedelta(minutes=10)
    ).update(last_seen_at=now)


# --- Compte dormant (S18) ---------------------------------------------------------------------


def is_dormant_login(*, user: User, install_id: str) -> bool:
    """Connexion depuis un appareil inconnu d'un compte inactif depuis plus de 60 j.

    Seules les sessions **non restreintes** prouvent l'activité ou un appareil connu : un
    titulaire de SIM recyclée ne peut pas se « blanchir » en se reconnectant (C1).
    """
    if user.dormant_restricted_since is not None:
        return True
    now = timezone.now()
    threshold = now - timedelta(days=settings.DORMANT_AFTER_DAYS)
    if user.created_at > threshold:
        return False
    trusted = DeviceSession.objects.filter(user=user, restricted=False)
    if trusted.filter(last_seen_at__gt=threshold).exists():
        return False
    install_id = clean_install_id(install_id)
    return not (install_id and trusted.filter(install_id=install_id).exists())


@transaction.atomic
def clear_dormant_restriction(*, user: User, actor: User, reason_code: str) -> int:
    """Levée par l'Ops après vérification (tâche 15). Auditée."""
    User.objects.filter(pk=user.pk).update(dormant_restricted_since=None, updated_at=timezone.now())
    sessions = list(
        DeviceSession.objects.select_for_update()
        .select_related("user")
        .filter(user=user, restricted=True, revoked_at__isnull=True)
    )
    for session in sessions:
        session.restricted = False
        session.save(update_fields=["restricted", "updated_at"])
        _clear_restricted_cache(session.public_id)
        transaction.on_commit(lambda s=session: _cache_fill(s))
    audit(
        action="accounts.dormant.cleared",
        actor=actor,
        actor_kind=AuditEvent.ActorKind.OPS,
        target=user,
        metadata={"reason_code": reason_code},
    )
    return len(sessions)


def _clear_restricted_cache(sid) -> None:
    """Retire l'entrée « restreinte » du cache, sans jamais effacer une pierre tombale."""
    with contextlib.suppress(redis.RedisError):
        key = _cache_key(sid)
        if (auth_redis().get(key) or b"").startswith(b"r:"):
            auth_redis().delete(key)
