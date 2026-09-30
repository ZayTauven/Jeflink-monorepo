"""Actions de l'équipe Ops sur les comptes (spec 001, « Endpoints » ``ops-accounts`` ; tâche 15).

Règles communes :
- **cible interdite** : son propre compte, un compte ops, un compte technique de l'admin Django
  (``403 ops_target_forbidden``). Ces cas passent par les commandes de gestion (deux Admin) ;
- chaque action porte un **motif énuméré** et une note facultative (280 caractères au plus,
  sans caractère de contrôle ni donnée personnelle, S14) ;
- chaque action est auditée, sans numéro en clair.
"""

import unicodedata

from django.db import transaction

from jeflink.common.errors import DomainError
from jeflink.common.pii import contains_pii, phone_hmac
from jeflink.trust.models import AuditEvent
from jeflink.trust.services import audit

from .models import DeviceSession, Role, User
from .otp_limits import phone_blocked_until, unblock_phone
from .phone import normalize_phone
from .selectors import has_role
from .sessions import clear_dormant_restriction, revoke_all_sessions

NOTE_MAX = 280

REASONS: dict[str, tuple[str, ...]] = {
    "reveal_phone": ("support_call", "kyc_review", "dispute", "legal_request"),
    "revoke_sessions": ("device_lost", "account_compromised", "user_request"),
    "unblock_otp": ("user_verified", "false_positive"),
    "deactivate": ("fraud", "user_request", "ops_other"),
    "reactivate": ("user_verified", "error_correction"),
    "clear_dormant": ("owner_verified", "kyc_verified"),
}


def clean_note(raw: str) -> str:
    """Note libre de l'Ops : courte, sans contrôle ni bidi, sans numéro ni jeton (S14)."""
    note = "".join(
        ch for ch in (raw or "") if unicodedata.category(ch) not in {"Cc", "Cf", "Co", "Cn"}
    )
    note = " ".join(note.split())
    if len(note) > NOTE_MAX or contains_pii(note):
        raise DomainError("note_invalid")
    return note


def _check_reason(action: str, reason_code: str) -> None:
    if reason_code not in REASONS[action]:
        raise DomainError("reason_invalid")


def _check_target(actor: User, target: User) -> None:
    if (
        target.pk == actor.pk
        or target.is_staff
        or target.is_superuser
        or has_role(target, Role.OPS)
    ):
        raise DomainError("ops_target_forbidden", status=403)


def _metadata(reason_code: str, note: str, **extra) -> dict:
    metadata = {"reason_code": reason_code, **extra}
    if note:
        metadata["note"] = note
    return metadata


def _locked_target(actor: User, public_id) -> User:
    target = User.objects.select_for_update(no_key=True).filter(public_id=public_id).first()
    if target is None:
        raise DomainError("not_found", status=404)
    _check_target(actor, target)
    return target


# --- Lecture ----------------------------------------------------------------------------------


def search_account(*, actor: User, raw_phone: str) -> User | None:
    """Recherche par numéro (en POST : jamais de numéro dans une URL, S14). 0 ou 1 résultat.

    Les comptes ops et techniques n'apparaissent jamais (ils ne sont pas des cibles).
    """
    phone = normalize_phone(raw_phone)
    user = User.objects.filter(phone=phone, deleted_at__isnull=True).first()
    if user is not None and (
        user.pk == actor.pk or user.is_staff or user.is_superuser or has_role(user, Role.OPS)
    ):
        user = None
    audit(
        action="ops.accounts.searched",
        actor=actor,
        actor_kind=AuditEvent.ActorKind.OPS,
        target=user,
        metadata={"phone_hmac": phone_hmac(phone), "found": user is not None},
    )
    return user


def account_for_ops(*, actor: User, public_id) -> User:
    target = User.objects.filter(public_id=public_id).first()
    if target is None:
        raise DomainError("not_found", status=404)
    _check_target(actor, target)
    return target


def reveal_phone(*, actor: User, public_id, reason_code: str, note: str = "") -> str:
    _check_reason("reveal_phone", reason_code)
    note = clean_note(note)
    target = account_for_ops(actor=actor, public_id=public_id)
    if not target.phone:
        raise DomainError("not_found", status=404)
    audit(
        action="ops.accounts.phone_revealed",
        actor=actor,
        actor_kind=AuditEvent.ActorKind.OPS,
        target=target,
        metadata=_metadata(reason_code, note),
    )
    return target.phone


def otp_block_until(target: User):
    return phone_blocked_until(target.phone) if target.phone else None


# --- Actions (manage : TOTP de moins de 5 min, S25) -------------------------------------------


@transaction.atomic
def ops_revoke_sessions(*, actor: User, public_id, reason_code: str, note: str = "") -> int:
    """Appareil perdu, plus aucun appareil (T2). Règle support : aucun agent ne demande un code."""
    _check_reason("revoke_sessions", reason_code)
    note = clean_note(note)
    target = _locked_target(actor, public_id)
    revoked = revoke_all_sessions(
        user=target, reason=DeviceSession.RevokedReason.OPS_REVOKED, actor=actor
    )
    audit(
        action="ops.accounts.sessions_revoked",
        actor=actor,
        actor_kind=AuditEvent.ActorKind.OPS,
        target=target,
        metadata=_metadata(reason_code, note, count=revoked),
    )
    return revoked


@transaction.atomic
def ops_unblock_otp(*, actor: User, public_id, reason_code: str, note: str = "") -> bool:
    """Lève le blocage OTP du numéro (risque résiduel S12 : blocage déclenché par un tiers)."""
    _check_reason("unblock_otp", reason_code)
    clean_note(note)
    target = _locked_target(actor, public_id)
    if not target.phone:
        raise DomainError("not_found", status=404)
    return unblock_phone(target.phone, actor=actor, reason_code=reason_code, target=target)


@transaction.atomic
def ops_deactivate(*, actor: User, public_id, reason_code: str, note: str = "") -> None:
    _check_reason("deactivate", reason_code)
    note = clean_note(note)
    target = _locked_target(actor, public_id)
    if target.is_deleted:
        raise DomainError("not_found", status=404)
    if not target.is_active:
        return  # idempotent
    target.is_active = False
    target.deactivation_reason = (
        User.DeactivationReason.FRAUD
        if reason_code == "fraud"
        else User.DeactivationReason.USER_REQUEST
        if reason_code == "user_request"
        else User.DeactivationReason.OPS_OTHER
    )
    target.deactivated_by = actor
    target.save(update_fields=["is_active", "deactivation_reason", "deactivated_by", "updated_at"])
    revoke_all_sessions(user=target, reason=DeviceSession.RevokedReason.ACCOUNT_DISABLED)
    audit(
        action="accounts.user.deactivated",
        actor=actor,
        actor_kind=AuditEvent.ActorKind.OPS,
        target=target,
        metadata=_metadata(reason_code, note),
    )


@transaction.atomic
def ops_reactivate(*, actor: User, public_id, reason_code: str, note: str = "") -> None:
    """Après ``fraud``, seul un Ops différent de celui qui a désactivé peut réactiver (S30)."""
    _check_reason("reactivate", reason_code)
    note = clean_note(note)
    target = _locked_target(actor, public_id)
    if target.is_deleted:
        raise DomainError("not_found", status=404)
    if target.is_active:
        return  # idempotent
    if (
        target.deactivation_reason == User.DeactivationReason.FRAUD
        and target.deactivated_by_id == actor.pk
    ):
        raise DomainError("ops_second_operator_required", status=403)
    previous = target.deactivation_reason
    target.is_active = True
    target.deactivation_reason = ""
    target.deactivated_by = None
    target.save(update_fields=["is_active", "deactivation_reason", "deactivated_by", "updated_at"])
    audit(
        action="accounts.user.reactivated",
        actor=actor,
        actor_kind=AuditEvent.ActorKind.OPS,
        target=target,
        metadata=_metadata(reason_code, note, previous_reason=previous),
    )


@transaction.atomic
def ops_clear_dormant(*, actor: User, public_id, reason_code: str, note: str = "") -> int:
    """« C'est bien mon compte » vérifié par le support (réservations récentes, KYC) (S18)."""
    _check_reason("clear_dormant", reason_code)
    clean_note(note)
    target = _locked_target(actor, public_id)
    if target.dormant_restricted_since is None:
        return 0
    return clear_dormant_restriction(user=target, actor=actor, reason_code=reason_code)
