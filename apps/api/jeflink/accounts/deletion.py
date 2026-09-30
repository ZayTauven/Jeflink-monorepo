"""Suppression du compte et « Repartir de zéro » (spec 001, « Données personnelles » ; S16, S18).

La suppression **anonymise** : la ligne ``User`` reste (clés étrangères, audit), mais plus rien
ne permet d'identifier la personne, et le numéro redevient libre.

Chaque domaine qui stocke des données personnelles enregistre un **anonymiseur**
(``register_anonymizer``) : c'est un critère « done » des specs suivantes. Un domaine peut aussi
refuser la suppression (``register_deletion_blocker``) : réservation en cours, solde de
portefeuille… Le refus est audité (``accounts.deletion.blocked``).
"""

from collections.abc import Callable
from datetime import timedelta

import redis
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from jeflink.common.errors import DomainError
from jeflink.common.pii import phone_hmac
from jeflink.common.ratelimit import client as auth_redis
from jeflink.trust.models import AuditEvent
from jeflink.trust.services import audit

from .mfa import clear_mfa
from .models import (
    DeviceSession,
    MfaChallenge,
    NoticeSms,
    OtpChallenge,
    PhoneChangeRequest,
    Role,
    RoleInvitation,
    User,
)
from .otp import consume_account_otp, request_account_otp
from .selectors import active_roles, has_role
from .services import revoke_role
from .sessions import TokenPair, create_session, revoke_all_sessions

Anonymizer = Callable[[User], None]
# Renvoie un code de motif (« booking_in_progress »…) si la suppression doit être refusée.
DeletionBlocker = Callable[[User], str | None]

_ANONYMIZERS: dict[str, Anonymizer] = {}
_BLOCKERS: dict[str, DeletionBlocker] = {}

# « Repartir de zéro » exige une connexion par code récente : la session restreinte vient
# juste d'être ouverte par l'OTP du nouveau titulaire du numéro.
FRESH_START_MAX_AUTH_AGE = timedelta(minutes=30)


def _register(registry: dict, name: str, fn: Callable, kind: str) -> None:
    current = registry.get(name)
    if current is not None and current is not fn:
        raise ValueError(f"{kind} déjà enregistré : {name}")
    registry[name] = fn


def register_anonymizer(domain: str, anonymizer: Anonymizer) -> None:
    """Appelé dans le ``ready()`` de chaque domaine qui stocke des données personnelles.

    Contrat (revue sécurité tâche 14, I2) :
    - l'anonymiseur s'exécute dans la transaction de la suppression, sous le verrou du compte,
      **avant** l'effacement du numéro : il peut encore le lire. Une exception annule tout ;
    - écritures en base seulement. Tout effet externe (fichiers S3, fournisseur) passe par
      ``transaction.on_commit`` puis une tâche Celery idempotente.
    """
    _register(_ANONYMIZERS, domain, anonymizer, "anonymiseur")


def register_deletion_blocker(domain: str, blocker: DeletionBlocker) -> None:
    """Refus de suppression (réservation en cours, solde de portefeuille…).

    Contrat (revue sécurité tâche 14, I2) : le domaine crée ses objets bloquants **sous le
    verrou du compte** (``User.objects.select_for_update(no_key=True)``) et vérifie
    ``is_active`` et ``deleted_at`` sur la ligne verrouillée, comme ``grant_role``. Sinon, un
    objet peut naître entre le contrôle et l'anonymisation.
    """
    _register(_BLOCKERS, domain, blocker, "bloqueur de suppression")


def _ops_blocker(user: User) -> str | None:
    # Un compte ops quitte d'abord son rôle (revoke_ops_role, deux Admin).
    return "ops_role" if has_role(user, Role.OPS) else None


def _recent_phone_change_blocker(user: User) -> str | None:
    # 72 h après un changement de numéro, pas de suppression : un compte tout juste pris ne
    # peut pas être effacé de façon irréversible (revue sécurité tâche 16, M9).
    changed = user.phone_changed_at
    if changed and timezone.now() - changed < PHONE_CHANGE_COOLDOWN:
        return "phone_recently_changed"
    return None


def _accounts_blockers(user: User) -> str | None:
    return _ops_blocker(user) or _recent_phone_change_blocker(user)


PHONE_CHANGE_COOLDOWN = timedelta(hours=72)
register_deletion_blocker("accounts", _accounts_blockers)


def deletion_blockers(user: User) -> list[str]:
    return sorted({reason for fn in _BLOCKERS.values() if (reason := fn(user))})


def _refuse(user: User, reasons: list[str]) -> None:
    """Lève le refus avec les motifs **déjà établis** (jamais recalculés après coup, I1).

    L'audit est écrit au plus une fois par heure et par compte : un compte bloqué ne peut pas
    inonder l'audit en rappelant l'endpoint (M6).
    """
    try:
        first = bool(auth_redis().set(f"jf:deletion_blocked:{user.public_id}", 1, nx=True, ex=3600))
    except redis.RedisError:
        first = True
    if first:
        audit(
            action="accounts.deletion.blocked",
            actor=user,
            actor_kind=AuditEvent.ActorKind.USER,
            target=user,
            metadata={"reasons": reasons},
            durable=True,
        )
    raise DomainError("account_deletion_blocked", status=409, reasons=reasons)


def _check_blockers(user: User) -> None:
    reasons = deletion_blockers(user)
    if reasons:
        _refuse(user, reasons)


# --- Anonymisation -------------------------------------------------------------------------------


def _anonymize(user: User, *, reason: str, session_public_id=None) -> None:
    """Efface tout ce qui identifie la personne. Appelée sous le verrou du compte.

    « Repartir de zéro » garde les invitations en attente vers ce numéro : elles visent la
    personne qui le détient **maintenant**, pas l'ancien titulaire (sans le nom proposé, qui
    pouvait être celui de l'ancien titulaire).
    """
    phone = user.phone or ""
    for anonymizer in _ANONYMIZERS.values():
        anonymizer(user)
    for role in active_roles(user):
        # Retirer owner clôt aussi les invitations envoyées par ce pro.
        revoke_role(user=user, role=role, reason_code="account_deleted")
    clear_mfa(user)
    MfaChallenge.objects.filter(user=user).update(device_label="", install_id="")
    user.groups.clear()
    user.user_permissions.clear()
    # Demandes de changement de numéro : ouvertes closes ; HMAC et notes effacés partout (M6).
    PhoneChangeRequest.objects.filter(user=user, status__in=PhoneChangeRequest.OPEN).update(
        status=PhoneChangeRequest.Status.EXPIRED, new_phone=""
    )
    PhoneChangeRequest.objects.filter(user=user).update(
        new_phone_hmac="", note="", updated_at=timezone.now()
    )
    OtpChallenge.objects.filter(user=user).delete()
    if phone:
        OtpChallenge.objects.filter(phone=phone).delete()
        pending = RoleInvitation.objects.filter(phone=phone, status=RoleInvitation.Status.PENDING)
        if reason == "fresh_start":
            pending.update(display_name_hint="", updated_at=timezone.now())
        else:
            # Closes, pas supprimées : le quota et l'audit de chaque pro restent cohérents (M4).
            pending.update(
                status=RoleInvitation.Status.EXPIRED, phone="", updated_at=timezone.now()
            )
        NoticeSms.objects.filter(phone_hmac=phone_hmac(phone)).exclude(phone="").delete()
    # Sessions en dernier, pierres tombales au commit seulement : un rollback ne déconnecte
    # personne. Après le commit, l'authentification refuse de toute façon un compte supprimé.
    revoke_all_sessions(
        user=user, reason=DeviceSession.RevokedReason.ACCOUNT_DELETED, immediate=False
    )
    DeviceSession.objects.filter(user=user).update(device_label="", install_id="")
    user.phone = None
    user.display_name = ""
    user.email = ""
    user.profile_status = User.ProfileStatus.GUEST
    user.is_active = False
    user.deactivation_reason = User.DeactivationReason.USER_REQUEST
    user.dormant_restricted_since = None
    user.deleted_at = timezone.now()
    user.set_unusable_password()
    user.save()
    audit(
        action="accounts.user.deleted",
        actor=user,
        actor_kind=AuditEvent.ActorKind.USER,
        target=user,
        session_public_id=session_public_id,
        metadata={"reason": reason},
    )


def _lock_active(user: User) -> User:
    user = User.objects.select_for_update(no_key=True).get(pk=user.pk)
    if not user.is_active or user.is_deleted:
        raise DomainError("account_disabled", status=403)
    return user


# --- Suppression par le titulaire (stores Apple et Google) ------------------------------------


def request_deletion_otp(*, user: User, app: str, idempotency_key: str, install_id: str) -> dict:
    """Code ``delete_account`` vers le numéro du compte. Refusé d'emblée si un domaine bloque :
    pas de SMS pour une suppression impossible."""
    _check_blockers(user)
    return request_account_otp(
        user=user,
        purpose=OtpChallenge.Purpose.DELETE_ACCOUNT,
        app=app,
        idempotency_key=idempotency_key,
        install_id=install_id,
    )


def delete_account(*, user: User, challenge_id, challenge_secret: str, code: str) -> None:
    _check_blockers(user)
    # Hors transaction : un échec de code reste compté (force brute), même si la suite échoue.
    challenge = consume_account_otp(
        user=user,
        purpose=OtpChallenge.Purpose.DELETE_ACCOUNT,
        challenge_id=challenge_id,
        challenge_secret=challenge_secret,
        code=code,
    )
    with transaction.atomic():
        user = _lock_active(user)
        # Numéro changé entre le code et la suppression : le code ne vaut plus (M9).
        if user.phone != challenge.phone:
            raise DomainError("otp_challenge_invalid")
        # Revérifié sous verrou : une réservation a pu naître entre-temps.
        reasons = deletion_blockers(user)
        if not reasons:
            _anonymize(user, reason="user_request")
    if reasons:
        _refuse(user, reasons)


# --- « Repartir de zéro » (compte dormant, S18) ----------------------------------------------


def fresh_start(*, user: User, session_public_id, auth_time: int | None) -> TokenPair:
    """Numéro peut-être recyclé : le nouveau titulaire abandonne l'ancien compte, qui est
    anonymisé, et reçoit un compte neuf sur ce numéro. Client seulement ; un pro attend la revue
    Ops. La session restreinte est remplacée par une session normale du nouveau compte.

    Non rejouable : si la réponse se perd, la session restreinte est déjà révoquée (401) et
    l'app renvoie vers la connexion, où le numéro mène au compte neuf.
    """
    now = timezone.now()
    if auth_time is None or now.timestamp() - auth_time > FRESH_START_MAX_AUTH_AGE.total_seconds():
        raise DomainError("reauth_required", status=403)
    with transaction.atomic():
        old = _lock_active(user)
        session = (
            DeviceSession.objects.select_for_update()
            .filter(public_id=session_public_id, user=old, revoked_at__isnull=True)
            .first()
        )
        if (
            session is None
            or not session.restricted
            or has_role(old, Role.OWNER, Role.TECHNICIAN, Role.OPS)
        ):
            raise DomainError("fresh_start_not_allowed", status=403)
        reasons = deletion_blockers(old)
        tokens = None
        if not reasons:
            phone = old.phone
            device = {
                "app": session.app,
                "platform": session.platform,
                "device_label": session.device_label,
                "install_id": session.install_id,
            }
            _anonymize(old, reason="fresh_start", session_public_id=session.public_id)
            new = User.objects.create_user(
                phone,
                phone_verified_at=now,
                terms_version=settings.TERMS_VERSION,
                terms_accepted_at=now,
            )
            audit(
                action="accounts.user.created",
                actor=new,
                target=new,
                metadata={"app": device["app"]},
            )
            tokens = create_session(user=new, **device)
    if tokens is None:
        _refuse(old, reasons)
    return tokens
