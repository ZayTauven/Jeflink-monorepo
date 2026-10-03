"""Changement de numéro par l'Ops (spec 001, « Numéro perdu pour de bon » ; S2 ; tâche 16).

1. Un Ops du groupe Admin (``ops.accounts.change_phone``) crée la demande, après la procédure
   écrite (réservations récentes pour un client, dossier KYC pour un pro).
2. Compte ``owner`` ou ``technician`` : un **second Ops** approuve. Client : pas d'approbation.
3. Un code ``change_phone`` part vers le **nouveau** numéro. L'utilisateur le saisit lui-même
   dans l'app (« J'ai changé de numéro ») ; l'Ops ne le voit jamais.
4. Numéro remplacé, toutes les sessions révoquées, SMS d'information à l'ancien numéro,
   ``phone_changed_at`` renseigné (``wallet`` imposera 72 h de refroidissement).

Ordre des verrous : compte, puis demande, puis challenge (comme le reste du domaine).
"""

import hmac
import secrets
from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone

from jeflink.common.alerts import alert_once
from jeflink.common.errors import DomainError
from jeflink.common.pii import phone_hmac
from jeflink.trust.models import AuditEvent
from jeflink.trust.services import audit

from .models import (
    DeviceSession,
    NoticeSms,
    OtpChallenge,
    OtpDelivery,
    PhoneChangeRequest,
    Role,
    User,
)
from .notices import queue_notice
from .ops import _check_target, _consume_quota, _locked_target, clean_note
from .otp import (
    CHALLENGE_TTL,
    VerifyResult,
    _code_matches,
    _enqueue,
    _register_failure,
    db_counts,
    hash_secret,
)
from .otp_limits import phone_blocked_until, record_verified, resend_delay, reserve_sms
from .phone import normalize_phone, phone_region
from .review_accounts import is_review_phone
from .selectors import has_role
from .sessions import account_allowed, create_session, revoke_all_sessions

REQUEST_TTL = timedelta(hours=24)
MAX_CODES = 3
REQUEST_REASONS = ("sim_lost_new_number", "number_changed", "operator_change")
REJECT_REASONS = ("proof_insufficient", "suspected_fraud", "request_error")


def _audit(action: str, *, actor: User, kind: str, target: User, request, **metadata) -> None:
    audit(
        action=action,
        actor=actor,
        actor_kind=kind,
        target=target,
        metadata={"request": str(request.public_id), **metadata},
    )


def _close(request: PhoneChangeRequest, status: str) -> None:
    """Demande close : le nouveau numéro est effacé, le code en cours ne vaut plus."""
    request.status = status
    request.new_phone = ""
    request.save(update_fields=["status", "new_phone", "updated_at"])
    _expire_challenge(request)


def _expire_challenge(request: PhoneChangeRequest) -> None:
    if request.challenge_id:
        OtpChallenge.objects.filter(
            pk=request.challenge_id, status=OtpChallenge.Status.PENDING
        ).update(status=OtpChallenge.Status.EXPIRED)


def _expire_stale(*, user: User, phone: str, now) -> None:
    """Demandes expirées du compte, ou qui visent ce même nouveau numéro (revue tâche 16, M5)."""
    stale = PhoneChangeRequest.objects.select_for_update().filter(
        Q(user=user) | Q(new_phone=phone),
        status__in=PhoneChangeRequest.OPEN,
        expires_at__lte=now,
    )
    for request in stale:
        _close(request, PhoneChangeRequest.Status.EXPIRED)


def _approval_still_valid(user: User, request: PhoneChangeRequest) -> bool:
    """Revérifié à chaque étape (revue tâche 16, I1) : un compte devenu pro depuis la demande
    exige un second Ops ; un compte devenu ops, technique ou de revue n'est plus une cible."""
    if user.is_staff or user.is_superuser or user.is_review_account or has_role(user, Role.OPS):
        return False
    is_pro = has_role(user, Role.OWNER, Role.TECHNICIAN)
    return not is_pro or request.approved_by_id is not None


def _back_to_approval(user: User, request: PhoneChangeRequest) -> None:
    """Le compte est devenu pro : plus de code tant qu'un second Ops n'a pas approuvé."""
    request.status = PhoneChangeRequest.Status.PENDING_APPROVAL
    request.requires_approval = True
    request.save(update_fields=["status", "requires_approval", "updated_at"])
    _expire_challenge(request)
    _audit(
        "accounts.phone_change.approval_required",
        actor=None,
        kind=AuditEvent.ActorKind.SYSTEM,
        target=user,
        request=request,
    )


def _send_code(request: PhoneChangeRequest, user: User, now) -> None:
    """Nouveau challenge ``change_phone`` vers le nouveau numéro (le précédent ne vaut plus)."""
    if request.codes_sent >= MAX_CODES:
        raise DomainError("phone_change_codes_exhausted", status=429)
    # Numéro pris entre-temps (inscription) : jamais de code « relier ce numéro » à un autre.
    if User.objects.filter(phone=request.new_phone).exists():
        raise DomainError("phone_in_use", status=409)
    if request.challenge_id:
        last = (
            OtpDelivery.objects.filter(challenge_id=request.challenge_id)
            .order_by("-created_at")
            .values_list("created_at", flat=True)
            .first()
        )
        available = last + timedelta(seconds=resend_delay(request.new_phone)) if last else now
        if now < available:
            wait = max(1, int((available - now).total_seconds()))
            raise DomainError("otp_resend_too_early", status=429, retry_after=wait)
    region = phone_region(request.new_phone)
    reserve_sms(phone=request.new_phone, region=region, new_challenge=True, fallback=db_counts)
    _expire_challenge(request)
    is_pro = has_role(user, Role.OWNER, Role.TECHNICIAN)
    challenge = OtpChallenge.objects.create(
        phone=request.new_phone,
        region=region,
        purpose=OtpChallenge.Purpose.CHANGE_PHONE,
        user=user,
        # Aucun secret n'est remis à personne : la confirmation passe par le numéro et le code.
        challenge_secret_hash=hash_secret(secrets.token_urlsafe(32)),
        app=DeviceSession.App.PRO if is_pro else DeviceSession.App.CLIENT,
        language=user.preferred_language,
        expires_at=now + CHALLENGE_TTL,
    )
    _enqueue(OtpDelivery.objects.create(challenge=challenge, attempt_no=1))
    request.challenge = challenge
    request.codes_sent += 1
    request.save(update_fields=["challenge", "codes_sent", "updated_at"])


def _lock_request(request_public_id) -> tuple[User, PhoneChangeRequest]:
    user_id = (
        PhoneChangeRequest.objects.filter(public_id=request_public_id)
        .values_list("user_id", flat=True)
        .first()
    )
    if user_id is None:
        raise DomainError("not_found", status=404)
    user = User.objects.select_for_update(no_key=True).get(pk=user_id)
    request = PhoneChangeRequest.objects.select_for_update().get(public_id=request_public_id)
    return user, request


def _open_request(request: PhoneChangeRequest, now) -> None:
    if request.status in PhoneChangeRequest.OPEN and request.expires_at <= now:
        _close(request, PhoneChangeRequest.Status.EXPIRED)
    if request.status not in PhoneChangeRequest.OPEN:
        raise DomainError("phone_change_closed", status=409)


# --- Côté Ops -------------------------------------------------------------------------------------


@transaction.atomic
def request_phone_change(
    *, actor: User, public_id, new_phone: str, reason_code: str, note: str = ""
) -> PhoneChangeRequest:
    if reason_code not in REQUEST_REASONS:
        raise DomainError("reason_invalid")
    note = clean_note(note)
    phone = normalize_phone(new_phone)
    if phone_region(phone) not in settings.OTP_ALLOWED_REGIONS:
        raise DomainError("phone_region_not_supported")
    user = _locked_target(actor, public_id)
    if user.is_deleted or not user.phone:
        raise DomainError("not_found", status=404)
    if not user.is_active:
        raise DomainError("account_disabled", status=409)
    if phone == user.phone:
        raise DomainError("phone_unchanged")
    # Numéro pris, ou numéro de revue des stores (SIM Jeflink) : jamais un nouveau numéro (M5).
    if User.objects.filter(phone=phone).exists() or is_review_phone(phone):
        raise DomainError("phone_in_use", status=409)
    # Quota bas par Ops : un Admin compromis ne change pas des numéros en série (I4).
    _consume_quota(actor, "phone_change")
    now = timezone.now()
    _expire_stale(user=user, phone=phone, now=now)
    if PhoneChangeRequest.objects.filter(user=user, status__in=PhoneChangeRequest.OPEN).exists():
        raise DomainError("phone_change_in_progress", status=409)
    requires_approval = has_role(user, Role.OWNER, Role.TECHNICIAN)
    try:
        with transaction.atomic():
            request = PhoneChangeRequest.objects.create(
                user=user,
                new_phone=phone,
                new_phone_hmac=phone_hmac(phone),
                requested_by=actor,
                requires_approval=requires_approval,
                reason_code=reason_code,
                note=note,
                status=(
                    PhoneChangeRequest.Status.PENDING_APPROVAL
                    if requires_approval
                    else PhoneChangeRequest.Status.APPROVED
                ),
                expires_at=now + REQUEST_TTL,
            )
    except IntegrityError as exc:
        # Une autre demande ouverte vise déjà ce nouveau numéro.
        raise DomainError("phone_in_use", status=409) from exc
    metadata = {"reason_code": reason_code, "new_phone_hmac": phone_hmac(phone)}
    if note:
        metadata["note"] = note
    _audit(
        "accounts.phone_change.requested",
        actor=actor,
        kind=AuditEvent.ActorKind.OPS,
        target=user,
        request=request,
        requires_approval=requires_approval,
        **metadata,
    )
    # Alerte à l'ancien numéro dès la demande : la victime peut réagir avant le changement.
    queue_notice(
        kind=NoticeSms.Kind.PHONE_CHANGE_REQUESTED,
        phone=user.phone,
        language=user.preferred_language,
    )
    if not requires_approval:
        # Un seul Ops suffit pour un client : chaque cas est signalé (I4).
        alert_once(
            f"phone_change_single:{request.public_id}", 86400, "phone_change_single_operator"
        )
        _send_code(request, user, now)
    return request


@transaction.atomic
def approve_phone_change(*, actor: User, request_public_id, new_phone: str) -> None:
    """Second Ops, différent du demandeur, pour un compte pro (S2).

    Il ressaisit le nouveau numéro complet, déclaré au dossier : l'approbation n'est pas une
    formalité sur un numéro masqué (revue tâche 16, I3). Le numéro n'est jamais affiché.
    """
    user, request = _lock_request(request_public_id)
    _check_target(actor, user, allow_review_account=False)
    now = timezone.now()
    _open_request(request, now)
    if request.status != PhoneChangeRequest.Status.PENDING_APPROVAL:
        raise DomainError("phone_change_closed", status=409)
    if request.requested_by_id == actor.pk:
        raise DomainError("ops_second_operator_required", status=403)
    try:
        presented = phone_hmac(normalize_phone(new_phone))
    except DomainError:
        presented = ""
    if not hmac.compare_digest(presented, request.new_phone_hmac):
        audit(
            action="accounts.phone_change.mismatch",
            actor=actor,
            actor_kind=AuditEvent.ActorKind.OPS,
            target=user,
            metadata={"request": str(request.public_id)},
            durable=True,
        )
        raise DomainError("phone_change_mismatch")
    _consume_quota(actor, "phone_change")
    request.approved_by = actor
    request.status = PhoneChangeRequest.Status.APPROVED
    request.save(update_fields=["approved_by", "status", "updated_at"])
    _audit(
        "accounts.phone_change.approved",
        actor=actor,
        kind=AuditEvent.ActorKind.OPS,
        target=user,
        request=request,
    )
    _send_code(request, user, now)


@transaction.atomic
def reject_phone_change(
    *, actor: User, request_public_id, reason_code: str, note: str = ""
) -> None:
    if reason_code not in REJECT_REASONS:
        raise DomainError("reason_invalid")
    note = clean_note(note)
    user, request = _lock_request(request_public_id)
    _check_target(actor, user, allow_review_account=False)
    _open_request(request, timezone.now())
    request.rejected_by = actor
    request.save(update_fields=["rejected_by", "updated_at"])
    _close(request, PhoneChangeRequest.Status.REJECTED)
    _audit(
        "accounts.phone_change.rejected",
        actor=actor,
        kind=AuditEvent.ActorKind.OPS,
        target=user,
        request=request,
        reason_code=reason_code,
        **({"note": note} if note else {}),
    )


@transaction.atomic
def resend_phone_change_code(*, actor: User, request_public_id) -> PhoneChangeRequest:
    """Code expiré ou SMS non reçu : nouveau code, 3 au plus, 60 s au moins entre deux.

    Si le compte est devenu pro depuis la demande, aucun code ne part : la demande repasse en
    attente d'un second Ops (statut renvoyé).
    """
    user, request = _lock_request(request_public_id)
    _check_target(actor, user, allow_review_account=False)
    now = timezone.now()
    _open_request(request, now)
    if request.status != PhoneChangeRequest.Status.APPROVED:
        raise DomainError("phone_change_closed", status=409)
    if not _approval_still_valid(user, request):
        _back_to_approval(user, request)
        return request
    _send_code(request, user, now)
    _audit(
        "accounts.phone_change.code_sent",
        actor=actor,
        kind=AuditEvent.ActorKind.OPS,
        target=user,
        request=request,
        attempt=request.codes_sent,
    )
    return request


def close_open_requests(*, user: User, actor: User | None, status: str) -> None:
    """Désactivation ou suppression du compte : les demandes ouvertes sont closes."""
    for request in PhoneChangeRequest.objects.select_for_update().filter(
        user=user, status__in=PhoneChangeRequest.OPEN
    ):
        if status == PhoneChangeRequest.Status.REJECTED and actor is not None:
            request.rejected_by = actor
            request.save(update_fields=["rejected_by", "updated_at"])
        _close(request, status)


# --- Côté utilisateur : « J'ai changé de numéro » -----------------------------------------------


def confirm_phone_change(
    *,
    new_phone: str,
    code: str,
    terms_version: str,
    app: str,
    platform: str,
    device_label: str = "",
    install_id: str = "",
) -> VerifyResult:
    """Saisie du code reçu sur le nouveau numéro. Seul un challenge ``change_phone`` en attente
    pour ce numéro est accepté. Numéro inconnu, code faux, challenge verrouillé ou expiré :
    même réponse ``otp_invalid``, sans rien révéler d'une demande en cours."""
    if terms_version != settings.TERMS_VERSION:
        raise DomainError("terms_not_accepted")
    invalid = DomainError("otp_invalid")
    phone = normalize_phone(new_phone)
    now = timezone.now()
    challenge = (
        OtpChallenge.objects.filter(
            phone=phone,
            purpose=OtpChallenge.Purpose.CHANGE_PHONE,
            status=OtpChallenge.Status.PENDING,
            expires_at__gt=now,
        )
        .order_by("-created_at")
        .first()
    )
    if challenge is None or phone_blocked_until(phone):
        raise invalid
    if not _code_matches(challenge, code, now=now):
        try:
            _register_failure(challenge)
        except DomainError:
            raise invalid from None
    with transaction.atomic():
        request = PhoneChangeRequest.objects.filter(challenge=challenge).first()
        if request is None:
            raise invalid
        user, request = _lock_request(request.public_id)
        if request.status != PhoneChangeRequest.Status.APPROVED or request.expires_at <= now:
            raise invalid
        # Rôles et cible revérifiés au moment d'agir (I1) : si le compte est devenu pro sans
        # second Ops, la demande repasse en attente (validé en base), et rien ne change.
        needs_approval = not _approval_still_valid(user, request)
        if needs_approval:
            _back_to_approval(user, request)
        else:
            tokens, user = _apply_change(
                user=user,
                request=request,
                challenge=challenge,
                phone=phone,
                now=now,
                device={
                    "app": app,
                    "platform": platform,
                    "device_label": device_label,
                    "install_id": install_id,
                },
            )
    if needs_approval:
        raise invalid
    record_verified(phone)
    return VerifyResult(user=user, tokens=tokens, is_new_user=False, restricted=False)


def _apply_change(*, user, request, challenge, phone, now, device) -> tuple:
    updated = OtpChallenge.objects.filter(
        pk=challenge.pk, status=OtpChallenge.Status.PENDING
    ).update(status=OtpChallenge.Status.VERIFIED, verified_at=now)
    if updated != 1:
        raise DomainError("otp_already_used", status=409)
    if not account_allowed(user):
        raise DomainError("account_disabled", status=403)
    if User.objects.filter(phone=phone).exclude(pk=user.pk).exists():
        raise DomainError("phone_in_use", status=409)
    old_phone = user.phone
    dormant_cleared = user.dormant_restricted_since is not None
    user.phone = phone
    user.phone_changed_at = now
    user.phone_verified_at = now
    # La procédure écrite a vérifié le titulaire : la règle du compte dormant est levée.
    user.dormant_restricted_since = None
    user.terms_version = settings.TERMS_VERSION
    user.terms_accepted_at = now
    try:
        with transaction.atomic():
            user.save(
                update_fields=[
                    "phone",
                    "phone_changed_at",
                    "phone_verified_at",
                    "dormant_restricted_since",
                    "terms_version",
                    "terms_accepted_at",
                    "updated_at",
                ]
            )
    except IntegrityError as exc:
        # Une inscription concurrente vient de prendre ce numéro (M3).
        raise DomainError("phone_in_use", status=409) from exc
    revoke_all_sessions(
        user=user, reason=DeviceSession.RevokedReason.PHONE_CHANGED, immediate=False
    )
    request.completed_at = now
    request.save(update_fields=["completed_at", "updated_at"])
    _close(request, PhoneChangeRequest.Status.COMPLETED)
    notice = None
    if old_phone:
        notice = queue_notice(
            kind=NoticeSms.Kind.PHONE_CHANGED, phone=old_phone, language=user.preferred_language
        )
    if notice is None:
        # Seule alerte de la victime : son absence est signalée à l'Ops (I2).
        alert_once(f"phone_changed_notice:{request.public_id}", 86400, "phone_changed_no_notice")
    _audit(
        "accounts.phone_change.completed",
        actor=user,
        kind=AuditEvent.ActorKind.USER,
        target=user,
        request=request,
        old_phone_hmac=phone_hmac(old_phone) if old_phone else "",
        dormant_cleared=dormant_cleared,
        notice_queued=notice is not None,
    )
    tokens = create_session(user=user, **device)
    return tokens, user
