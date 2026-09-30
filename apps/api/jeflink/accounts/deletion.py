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

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from jeflink.common.errors import DomainError
from jeflink.common.pii import phone_hmac
from jeflink.trust.models import AuditEvent
from jeflink.trust.services import audit

from .mfa import clear_mfa
from .models import (
    DeviceSession,
    NoticeSms,
    OtpChallenge,
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

    L'anonymiseur s'exécute dans la transaction de la suppression, **avant** l'effacement du
    numéro : il peut encore le lire. Une exception annule toute la suppression.
    """
    _register(_ANONYMIZERS, domain, anonymizer, "anonymiseur")


def register_deletion_blocker(domain: str, blocker: DeletionBlocker) -> None:
    _register(_BLOCKERS, domain, blocker, "bloqueur de suppression")


def _ops_blocker(user: User) -> str | None:
    # Un compte ops quitte d'abord son rôle (revoke_ops_role, deux Admin).
    return "ops_role" if has_role(user, Role.OPS) else None


register_deletion_blocker("accounts", _ops_blocker)


def deletion_blockers(user: User) -> list[str]:
    return sorted({reason for fn in _BLOCKERS.values() if (reason := fn(user))})


def _check_blockers(user: User) -> None:
    reasons = deletion_blockers(user)
    if reasons:
        audit(
            action="accounts.deletion.blocked",
            actor=user,
            actor_kind=AuditEvent.ActorKind.USER,
            target=user,
            metadata={"reasons": reasons},
            durable=True,
        )
        raise DomainError("account_deletion_blocked", status=409, reasons=reasons)


# --- Anonymisation -------------------------------------------------------------------------------


def _anonymize(user: User, *, reason: str) -> None:
    """Efface tout ce qui identifie la personne. Appelée sous le verrou du compte.

    « Repartir de zéro » garde les invitations en attente vers ce numéro : elles visent la
    personne qui le détient **maintenant**, pas l'ancien titulaire.
    """
    phone = user.phone or ""
    for anonymizer in _ANONYMIZERS.values():
        anonymizer(user)
    revoke_all_sessions(user=user, reason=DeviceSession.RevokedReason.ACCOUNT_DELETED)
    # Libellés et identifiants d'appareil, y compris des sessions déjà révoquées.
    DeviceSession.objects.filter(user=user).update(device_label="", install_id="")
    for role in active_roles(user):
        # Retirer owner clôt aussi les invitations envoyées par ce pro.
        revoke_role(user=user, role=role, reason_code="account_deleted")
    clear_mfa(user)
    user.groups.clear()
    OtpChallenge.objects.filter(user=user).delete()
    if phone:
        OtpChallenge.objects.filter(phone=phone).delete()
        if reason != "fresh_start":
            RoleInvitation.objects.filter(phone=phone).delete()
        NoticeSms.objects.filter(phone_hmac=phone_hmac(phone)).exclude(phone="").delete()
    now = timezone.now()
    user.phone = None
    user.display_name = ""
    user.email = ""
    user.profile_status = User.ProfileStatus.GUEST
    user.is_active = False
    user.deactivation_reason = User.DeactivationReason.USER_REQUEST
    user.dormant_restricted_since = None
    user.deleted_at = now
    user.set_unusable_password()
    user.save()
    audit(
        action="accounts.user.deleted",
        actor=user,
        actor_kind=AuditEvent.ActorKind.USER,
        target=user,
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
    consume_account_otp(
        user=user,
        purpose=OtpChallenge.Purpose.DELETE_ACCOUNT,
        challenge_id=challenge_id,
        challenge_secret=challenge_secret,
        code=code,
    )
    with transaction.atomic():
        user = _lock_active(user)
        # Revérifié sous verrou : une réservation a pu naître entre-temps.
        reasons = deletion_blockers(user)
        if not reasons:
            _anonymize(user, reason="user_request")
    if reasons:
        _check_blockers(user)


# --- « Repartir de zéro » (compte dormant, S18) ----------------------------------------------


def fresh_start(*, user: User, session_public_id, auth_time: int | None) -> TokenPair:
    """Numéro peut-être recyclé : le nouveau titulaire abandonne l'ancien compte, qui est
    anonymisé, et reçoit un compte neuf sur ce numéro. Client seulement ; un pro attend la revue
    Ops. La session restreinte est remplacée par une session normale du nouveau compte."""
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
        if deletion_blockers(old):
            blocked = True
        else:
            blocked = False
            phone = old.phone
            device = {
                "app": session.app,
                "platform": session.platform,
                "device_label": session.device_label,
                "install_id": session.install_id,
            }
            _anonymize(old, reason="fresh_start")
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
    if blocked:
        _check_blockers(old)  # audite puis lève account_deletion_blocked
    return tokens
