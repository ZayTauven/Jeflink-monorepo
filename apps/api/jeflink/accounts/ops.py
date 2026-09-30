"""Actions de l'équipe Ops sur les comptes (spec 001, « Endpoints » ``ops-accounts`` ; tâche 15).

Règles communes :
- **cible interdite** : son propre compte, un compte ops, un compte technique de l'admin Django
  (``403 ops_target_forbidden``). Ces cas passent par les commandes de gestion (deux Admin) ;
- chaque action porte un **motif énuméré** et une note facultative (280 caractères au plus,
  sans caractère de contrôle ni donnée personnelle, S14) ;
- chaque action est auditée, sans numéro en clair.
"""

import re
import unicodedata

from django.conf import settings
from django.db import transaction

from jeflink.common.alerts import alert_once
from jeflink.common.errors import DomainError
from jeflink.common.pii import contains_pii, phone_hmac
from jeflink.common.ratelimit import Limit, RateLimitUnavailable, consume, count
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


_DIGIT_RUN = re.compile(r"\d(?:[\s./()+-]*\d){6,}")
_EMAIL = re.compile(r"[^\s@]+@[^\s@]+\.[^\s@]+")


def clean_note(raw: str) -> str:
    """Note libre de l'Ops : courte, sans contrôle ni bidi, sans donnée personnelle (S14).

    Normalisée (NFKC : les chiffres pleine chasse deviennent ASCII), puis refusée si elle
    contient une suite d'au moins 7 chiffres (numéro, pièce d'identité), un e-mail ou un jeton.
    Elle reste 5 ans dans l'audit (revue tâche 15, M3).
    """
    note = unicodedata.normalize("NFKC", raw or "")
    note = "".join(ch for ch in note if unicodedata.category(ch) not in {"Cc", "Cf", "Co", "Cn"})
    note = " ".join(note.split())
    if len(note) > NOTE_MAX or contains_pii(note) or _DIGIT_RUN.search(note) or _EMAIL.search(note):
        raise DomainError("note_invalid")
    return note


def _check_reason(action: str, reason_code: str) -> None:
    if reason_code not in REASONS[action]:
        raise DomainError("reason_invalid")


def _check_target(actor: User, target: User, *, allow_review_account: bool = True) -> None:
    """Jamais soi-même, un Ops ou un compte technique. Le compte de revue des stores (S17) n'est
    ouvert qu'à la lecture et à la désactivation, coupe-circuit (revue tâche 15, M4)."""
    if (
        target.pk == actor.pk
        or target.is_staff
        or target.is_superuser
        or has_role(target, Role.OPS)
        or (target.is_review_account and not allow_review_account)
    ):
        raise DomainError("ops_target_forbidden", status=403)


def _consume_quota(actor: User, scope: str) -> None:
    """Quota par Ops (heure et jour). Sans Redis, refus : jamais d'ouverture (comme l'OTP)."""
    limits = [
        Limit(f"ops:{scope}_{window}", limit, window)
        for limit, window in settings.OPS_QUOTAS[scope]
    ]
    identity = str(actor.public_id)
    try:
        outcome = consume([(limit, identity) for limit in limits])
        daily = limits[-1]
        used = count(daily, identity)
    except RateLimitUnavailable as exc:
        raise DomainError("ops_quota_unavailable", status=503) from exc
    if not outcome.allowed:
        alert_once(f"ops_quota:{scope}:{identity}", 3600, "ops_quota_exceeded", scope=scope)
        audit(
            action="ops.accounts.quota_exceeded",
            actor=actor,
            actor_kind=AuditEvent.ActorKind.OPS,
            metadata={"scope": scope},
            durable=True,
        )
        raise DomainError("ops_rate_limited", status=429, retry_after=outcome.retry_after)
    if used * 2 >= daily.limit:
        alert_once(f"ops_quota_half:{scope}:{identity}", 86400, "ops_quota_half", scope=scope)


def _is_admin(actor: User) -> bool:
    return actor.groups.filter(name="Admin").exists()


def _metadata(reason_code: str, note: str, **extra) -> dict:
    metadata = {"reason_code": reason_code, **extra}
    if note:
        metadata["note"] = note
    return metadata


def _locked_target(actor: User, public_id, *, allow_review_account: bool = False) -> User:
    target = User.objects.select_for_update(no_key=True).filter(public_id=public_id).first()
    if target is None:
        raise DomainError("not_found", status=404)
    _check_target(actor, target, allow_review_account=allow_review_account)
    return target


# --- Lecture ----------------------------------------------------------------------------------


def search_account(*, actor: User, raw_phone: str) -> User | None:
    """Recherche par numéro (en POST : jamais de numéro dans une URL, S14). 0 ou 1 résultat.

    Les comptes ops et techniques n'apparaissent jamais (ils ne sont pas des cibles).
    """
    phone = normalize_phone(raw_phone)
    _consume_quota(actor, "search")
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


def account_for_ops(*, actor: User, public_id, audited: bool = False) -> User:
    target = User.objects.filter(public_id=public_id).first()
    if target is None:
        raise DomainError("not_found", status=404)
    _check_target(actor, target)
    if audited:
        # Consultation de la fiche tracée, sans métadonnée personnelle (revue tâche 15, M5).
        audit(
            action="ops.accounts.viewed",
            actor=actor,
            actor_kind=AuditEvent.ActorKind.OPS,
            target=target,
            metadata={},
        )
    return target


def reveal_phone(*, actor: User, public_id, reason_code: str, note: str = "") -> str:
    _check_reason("reveal_phone", reason_code)
    note = clean_note(note)
    target = account_for_ops(actor=actor, public_id=public_id)
    _check_target(actor, target, allow_review_account=False)
    if not target.phone:
        raise DomainError("not_found", status=404)
    _consume_quota(actor, "reveal_phone")
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
    note = clean_note(note)
    target = _locked_target(actor, public_id)
    if not target.phone:
        raise DomainError("not_found", status=404)
    if not unblock_phone(
        target.phone, actor=actor, reason_code=reason_code, target=target, note=note
    ):
        # Rien à lever : réponse explicite plutôt qu'un succès muet (revue tâche 15, M2).
        raise DomainError("otp_not_blocked", status=409)
    return True


@transaction.atomic
def ops_deactivate(*, actor: User, public_id, reason_code: str, note: str = "") -> None:
    _check_reason("deactivate", reason_code)
    note = clean_note(note)
    target = _locked_target(actor, public_id, allow_review_account=True)
    if target.is_deleted:
        raise DomainError("not_found", status=404)
    previous = target.deactivation_reason
    if not target.is_active and (
        reason_code != "fraud" or previous == User.DeactivationReason.FRAUD
    ):
        # Une fraude découverte après une autre désactivation est enregistrée avec son auteur :
        # sinon l'Ops qui avait désactivé pour un autre motif réactiverait seul (S30, I3).
        raise DomainError("account_already_inactive", status=409)
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
        metadata=_metadata(
            reason_code, note, **({"previous_reason": previous} if previous else {})
        ),
    )


@transaction.atomic
def ops_reactivate(*, actor: User, public_id, reason_code: str, note: str = "") -> None:
    """Après ``fraud``, seul un Ops différent de celui qui a désactivé peut réactiver (S30)."""
    _check_reason("reactivate", reason_code)
    note = clean_note(note)
    target = _locked_target(actor, public_id, allow_review_account=True)
    if target.is_deleted:
        raise DomainError("not_found", status=404)
    if target.is_active:
        raise DomainError("account_already_active", status=409)
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
    note = clean_note(note)
    target = _locked_target(actor, public_id)
    if target.dormant_restricted_since is None:
        raise DomainError("account_not_dormant", status=409)
    # Compte pro : rendu à la personne qui détient la SIM, au même risque qu'un changement de
    # numéro. Réservé au groupe Admin (décision de Zay, revue tâche 15, I4).
    if has_role(target, Role.OWNER, Role.TECHNICIAN) and not _is_admin(actor):
        raise DomainError("ops_admin_required", status=403)
    return clear_dormant_restriction(user=target, actor=actor, reason_code=reason_code, note=note)
