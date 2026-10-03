"""Écritures du domaine accounts : les autres domaines passent par ici, jamais par les modèles."""

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from jeflink.common.errors import DomainError
from jeflink.common.pii import phone_hmac
from jeflink.trust.models import AuditEvent
from jeflink.trust.services import audit

from .models import NoticeSms, Role, RoleGrant, RoleInvitation, User
from .notices import queue_notice
from .phone import normalize_phone, phone_display, phone_region
from .selectors import has_role, pending_invitations_for
from .validators import clean_display_name

__all__ = [
    "AcceptedInvitation",
    "accept_invitation",
    "decline_invitation",
    "expire_invitations_from",
    "grant_role",
    "invite_to_role",
    "normalize_phone",
    "phone_display",
    "phone_region",
    "register_invitation_handler",
    "revoke_role",
    "update_profile",
]


@transaction.atomic
def update_profile(
    *,
    user: User,
    display_name: str | None = None,
    email: str | None = None,
    preferred_language: str | None = None,
) -> User:
    """Mise à jour du profil par son titulaire. ``None`` laisse le champ inchangé.

    Donner un nom fait passer l'invité à complet. Le nom ne peut pas être vidé : un profil
    complet ne redevient jamais invité. L'e-mail est informatif, jamais vérifié ni utilisé
    pour la récupération (S27) ; une chaîne vide l'efface.
    """
    user = User.objects.select_for_update(no_key=True).get(pk=user.pk)
    # Relu sur la ligne verrouillée : une suppression ou une désactivation concurrente gagne.
    if not user.is_active or user.is_deleted:
        raise DomainError("account_disabled", status=403)
    changed: list[str] = []
    if display_name is not None:
        user.display_name = clean_display_name(display_name)
        user.profile_status = User.ProfileStatus.COMPLETE
        changed += ["display_name", "profile_status"]
    if email is not None:
        user.email = User.objects.normalize_email(email.strip())
        changed.append("email")
    if preferred_language is not None:
        if preferred_language not in User.Language.values:
            raise DomainError("language_invalid")
        user.preferred_language = preferred_language
        changed.append("preferred_language")
    if changed:
        user.save(update_fields=[*changed, "updated_at"])
    return user


@transaction.atomic
def grant_role(
    *,
    user: User,
    role: str,
    reason_code: str,
    granted_by: User | None = None,
    operator: str = "",
    second_operator: str = "",
    actor: User | None = None,
    actor_kind: str | None = None,
) -> RoleGrant:
    """Accorde un rôle (idempotent). Refusé sur un compte de revue, désactivé ou supprimé.

    L'acteur audité est ``granted_by`` (Ops) par défaut ; une invitation acceptée passe
    l'utilisateur lui-même (``actor``, ``actor_kind=user``).
    """
    if role not in Role.values:
        raise DomainError("role_unknown")
    # Verrou sur le compte, puis contrôles sur la ligne verrouillée (M1) : deux attributions
    # concurrentes ne créent qu'un RoleGrant, et l'état lu est celui de la base.
    user = User.objects.select_for_update(no_key=True).get(pk=user.pk)
    # Compte de revue des stores (S17) et comptes techniques de l'admin Django (M3).
    if user.is_review_account or user.is_staff or user.is_superuser:
        raise DomainError("role_not_allowed", status=403)
    if not user.is_active or user.is_deleted:
        raise DomainError("account_disabled", status=403)
    existing = RoleGrant.objects.filter(user=user, role=role, revoked_at__isnull=True).first()
    if existing:
        return existing
    grant = RoleGrant.objects.create(
        user=user, role=role, granted_by=granted_by, reason_code=reason_code
    )
    audit(
        action="accounts.role.granted",
        actor=actor or granted_by,
        actor_kind=actor_kind or _actor_kind(granted_by, operator),
        target=user,
        metadata=_role_metadata(role, reason_code, operator, second_operator),
    )
    return grant


@transaction.atomic
def revoke_role(
    *,
    user: User,
    role: str,
    reason_code: str,
    revoked_by: User | None = None,
    operator: str = "",
    second_operator: str = "",
) -> bool:
    """Retire un rôle actif. Renvoie False s'il n'y en avait pas."""
    updated = RoleGrant.objects.filter(user=user, role=role, revoked_at__isnull=True).update(
        revoked_at=timezone.now(), revoked_by=revoked_by
    )
    if not updated:
        return False
    if role == Role.OWNER:
        expire_invitations_from(user)
    audit(
        action="accounts.role.revoked",
        actor=revoked_by,
        actor_kind=_actor_kind(revoked_by, operator),
        target=user,
        metadata=_role_metadata(role, reason_code, operator, second_operator),
    )
    return True


def _actor_kind(actor: User | None, operator: str) -> str:
    if actor is not None or operator:
        return AuditEvent.ActorKind.OPS
    return AuditEvent.ActorKind.SYSTEM


def _role_metadata(role: str, reason_code: str, operator: str, second_operator: str) -> dict:
    metadata = {"role": role, "reason_code": reason_code}
    if operator:
        metadata["operator"] = operator
    if second_operator:
        metadata["second_operator"] = second_operator
    return metadata


# --- Invitations (S19) -------------------------------------------------------------------------


@dataclass(frozen=True)
class AcceptedInvitation:
    """Ce que reçoit le gestionnaire de providers quand une invitation est acceptée."""

    public_id: uuid.UUID
    role: str
    context_ref: uuid.UUID
    user: User
    invited_by: User


InvitationHandler = Callable[[AcceptedInvitation], None]
_INVITATION_HANDLERS: dict[str, InvitationHandler] = {}
PRO_ROLES = frozenset({Role.OWNER, Role.TECHNICIAN})
# Après un refus, le même pro ne renvoie plus de SMS à ce numéro pendant 30 jours (revue, M2).
DECLINE_SMS_COOLDOWN = timedelta(days=30)


def register_invitation_handler(role: str, handler: InvitationHandler) -> None:
    """Appelé par providers dans son ``ready()`` : crée l'appartenance à l'équipe à l'acceptation.

    Le gestionnaire s'exécute dans la transaction de l'acceptation : une ``DomainError`` qu'il
    lève annule tout (aucun rôle accordé). Sans gestionnaire, aucune invitation ne peut être
    acceptée. accounts n'importe jamais providers.
    """
    if role not in PRO_ROLES:
        raise ValueError(f"rôle d'invitation inconnu : {role}")
    current = _INVITATION_HANDLERS.get(role)
    if current is not None and current is not handler:
        raise ValueError(f"gestionnaire d'invitation déjà enregistré pour {role}")
    _INVITATION_HANDLERS[role] = handler


def _check_inviter(inviter: User, phone: str) -> None:
    """Seul un gérant (``owner``) actif, ni technique ni compte de revue, invite (revue, I1)."""
    if not inviter.is_active or inviter.is_deleted:
        raise DomainError("account_disabled", status=403)
    if (
        inviter.is_review_account
        or inviter.is_staff
        or inviter.is_superuser
        or not has_role(inviter, Role.OWNER)
    ):
        raise DomainError("role_required", status=403)
    if inviter.phone == phone:
        raise DomainError("invitation_self")


def _check_inviter_quota(inviter: User, now: datetime) -> None:
    """20 invitations par jour et par pro, comptées en base sous le verrou du pro (sans Redis)."""
    recent = RoleInvitation.objects.filter(
        invited_by=inviter, created_at__gte=now - timedelta(days=1)
    )
    if recent.count() < settings.INVITATIONS_PER_INVITER_DAILY:
        return
    oldest = recent.order_by("created_at").values_list("created_at", flat=True).first()
    retry_after = max(1, int((oldest + timedelta(days=1) - now).total_seconds()))
    raise DomainError("invitation_rate_limited", status=429, retry_after=retry_after)


def _pending(phone: str, role: str, context_ref: uuid.UUID):
    return RoleInvitation.objects.filter(
        phone=phone, role=role, context_ref=context_ref, status=RoleInvitation.Status.PENDING
    )


def invite_to_role(
    *,
    phone: str,
    role: str,
    invited_by: User,
    context_ref: uuid.UUID,
    display_name_hint: str = "",
) -> RoleInvitation:
    """Crée une invitation en attente et prévient le numéro par un SMS générique (S19).

    Aucun ``User`` n'est consulté ni créé : la réponse ne dépend pas de l'existence d'un compte.
    Réinviter pendant qu'une invitation vit la renvoie telle quelle, sans nouveau SMS. Le SMS
    est envoyé au mieux (voir ``notices``) : un budget épuisé n'échoue jamais ici.
    """
    if role not in PRO_ROLES:
        raise DomainError("role_unknown")
    phone = normalize_phone(phone)
    if phone_region(phone) not in settings.OTP_ALLOWED_REGIONS:
        raise DomainError("phone_region_not_supported")
    hint = clean_display_name(display_name_hint) if display_name_hint.strip() else ""
    hashed = phone_hmac(phone)
    with transaction.atomic():
        # Verrou du pro : sérialise ses invitations, donc son quota quotidien.
        inviter = User.objects.select_for_update(no_key=True).get(pk=invited_by.pk)
        _check_inviter(inviter, phone)
        now = timezone.now()
        existing = _pending(phone, role, context_ref).select_for_update().first()
        if existing is not None and existing.expires_at > now:
            return existing
        if existing is not None:
            existing.status = RoleInvitation.Status.EXPIRED
            existing.phone = ""
            existing.save(update_fields=["status", "phone", "updated_at"])
        _check_inviter_quota(inviter, now)
        try:
            with transaction.atomic():
                invitation = RoleInvitation.objects.create(
                    phone=phone,
                    phone_hmac=hashed,
                    role=role,
                    invited_by=inviter,
                    display_name_hint=hint,
                    context_ref=context_ref,
                    expires_at=now + timedelta(days=settings.INVITATION_TTL_DAYS),
                )
        except IntegrityError:
            # Deux gérants de la même équipe invitent le même numéro au même instant (revue, M8).
            return _pending(phone, role, context_ref).get()
        recently_declined = RoleInvitation.objects.filter(
            invited_by=inviter,
            phone_hmac=hashed,
            status=RoleInvitation.Status.DECLINED,
            declined_at__gt=now - DECLINE_SMS_COOLDOWN,
        ).exists()
        notice = (
            None if recently_declined else queue_notice(kind=NoticeSms.Kind.INVITATION, phone=phone)
        )
        audit(
            action="accounts.invitation.created",
            actor=inviter,
            actor_kind=AuditEvent.ActorKind.USER,
            metadata={
                "role": role,
                "invitation": str(invitation.public_id),
                "phone_hmac": hashed,
                "sms_queued": notice is not None,
            },
        )
    return invitation


def _locked_account(user: User) -> User:
    user = User.objects.select_for_update(no_key=True).get(pk=user.pk)
    if not user.is_active or user.is_deleted:
        raise DomainError("account_disabled", status=403)
    return user


def _locked_pending_invitation(user: User, invitation_public_id) -> RoleInvitation | None:
    """Invitation en attente du numéro du compte, verrouillée, ou None."""
    return (
        pending_invitations_for(user)
        .select_for_update(of=("self",))
        .filter(public_id=invitation_public_id)
        .first()
    )


def _closed_by(user: User, invitation_public_id, status: str) -> RoleInvitation | None:
    """Invitation déjà close par ce compte : rejouer accept/decline renvoie le même succès (I4)."""
    closed = RoleInvitation.objects.filter(public_id=invitation_public_id, status=status)
    if status == RoleInvitation.Status.ACCEPTED:
        return closed.filter(accepted_by=user).first()
    if not user.phone:
        return None
    return closed.filter(phone_hmac=phone_hmac(user.phone)).first()


@transaction.atomic
def accept_invitation(
    *, user: User, invitation_public_id, display_name: str = ""
) -> RoleGrant | None:
    """Acceptation explicite par le titulaire du numéro : rôle accordé, providers prévenu.

    Un profil invité est complété par ``display_name`` (saisi ou confirmé par l'invité sur
    l'écran d'acceptation), à défaut par le nom proposé par le pro ; sinon ``profile_incomplete``.
    Rejouer une acceptation déjà faite renvoie le même succès. Autre cas → 404 (S5).
    """
    user = _locked_account(user)
    invitation = _locked_pending_invitation(user, invitation_public_id)
    if invitation is None:
        if _closed_by(user, invitation_public_id, RoleInvitation.Status.ACCEPTED) is not None:
            return None
        raise DomainError("not_found", status=404)
    handler = _INVITATION_HANDLERS.get(invitation.role)
    if handler is None:
        # Sans providers, un rôle accordé ne serait rattaché à aucune équipe (revue, I2).
        raise DomainError("invitation_unavailable", status=503)
    if user.profile_status != User.ProfileStatus.COMPLETE:
        name = display_name.strip() or invitation.display_name_hint
        if not name:
            raise DomainError("profile_incomplete", status=403)
        user.display_name = clean_display_name(name)
        user.profile_status = User.ProfileStatus.COMPLETE
        user.save(update_fields=["display_name", "profile_status", "updated_at"])
    grant = grant_role(
        user=user,
        role=invitation.role,
        reason_code="invitation_accepted",
        granted_by=invitation.invited_by,
        actor=user,
        actor_kind=AuditEvent.ActorKind.USER,
    )
    invitation.status = RoleInvitation.Status.ACCEPTED
    invitation.accepted_at = timezone.now()
    invitation.accepted_by = user
    invitation.phone = ""
    invitation.save(update_fields=["status", "accepted_at", "accepted_by", "phone", "updated_at"])
    handler(
        AcceptedInvitation(
            public_id=invitation.public_id,
            role=invitation.role,
            context_ref=invitation.context_ref,
            user=user,
            invited_by=invitation.invited_by,
        )
    )
    audit(
        action="accounts.invitation.accepted",
        actor=user,
        actor_kind=AuditEvent.ActorKind.USER,
        target=user,
        metadata=_invitation_metadata(invitation),
    )
    return grant


@transaction.atomic
def decline_invitation(*, user: User, invitation_public_id) -> None:
    user = _locked_account(user)
    invitation = _locked_pending_invitation(user, invitation_public_id)
    if invitation is None:
        if _closed_by(user, invitation_public_id, RoleInvitation.Status.DECLINED) is not None:
            return
        raise DomainError("not_found", status=404)
    invitation.status = RoleInvitation.Status.DECLINED
    invitation.declined_at = timezone.now()
    invitation.phone = ""
    invitation.save(update_fields=["status", "declined_at", "phone", "updated_at"])
    audit(
        action="accounts.invitation.declined",
        actor=user,
        actor_kind=AuditEvent.ActorKind.USER,
        target=user,
        metadata=_invitation_metadata(invitation),
    )


def _invitation_metadata(invitation: RoleInvitation) -> dict:
    return {
        "role": invitation.role,
        "invitation": str(invitation.public_id),
        "invited_by": str(invitation.invited_by.public_id),
    }


def expire_invitations_from(inviter: User) -> int:
    """Invitations en attente d'un pro qui perd son rôle de gérant : closes, numéro effacé (I1)."""
    return RoleInvitation.objects.filter(
        invited_by=inviter, status=RoleInvitation.Status.PENDING
    ).update(status=RoleInvitation.Status.EXPIRED, phone="", updated_at=timezone.now())
