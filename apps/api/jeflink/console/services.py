"""Actions de l'équipe dans la console. Chacune est journalisée (``AuditLog``).

Les changements de statut d'une demande ou d'un litige restent dans ``jobs.services`` ; ce module
les appelle puis écrit le journal.
"""

from django.db import transaction
from django.utils import timezone
from rest_framework.authtoken.models import Token
from rest_framework.exceptions import PermissionDenied, ValidationError

from jeflink.accounts.models import ContactMessage, ProProfile, User
from jeflink.jobs import services as jobs
from jeflink.jobs.models import Dispute, Quote, Review, ServiceRequest

from .models import AuditLog

A = AuditLog.Action


def _staff(user):
    """Garde-fou : ces actions ne sont permises qu'à l'équipe, même appelées hors des vues."""
    if not user.is_staff:
        raise PermissionDenied("Réservé à l'équipe Jeflink.")


def _withdraw_pending_quotes(pro: User):
    """Les devis en attente d'un pro suspendu ou dé-vérifié ne peuvent plus être choisis."""
    Quote.objects.filter(pro=pro, status=Quote.Status.PENDING).update(status=Quote.Status.DECLINED)


def log(actor, action: str, target_type: str, target_id: int, label: str, details: str = ""):
    return AuditLog.objects.create(
        actor=actor,
        action=action,
        target_type=target_type,
        target_id=target_id,
        target_label=str(label)[:200],
        details=details[:300],
    )


def _required(text: str, message: str) -> str:
    text = (text or "").strip()
    if not text:
        raise ValidationError(message)
    return text


# --- Pros et comptes ---------------------------------------------------------------------------


@transaction.atomic
def verify_pro(staff, profile: ProProfile) -> ProProfile:
    _staff(staff)
    if profile.is_verified:
        raise ValidationError("Ce pro est déjà vérifié.")
    if not profile.trades.exists():
        raise ValidationError("Ce pro n'a déclaré aucun métier : impossible de le vérifier.")
    profile.is_verified = True
    profile.verified_at = timezone.now()
    profile.verification_note = ""
    profile.save(update_fields=["is_verified", "verified_at", "verification_note"])
    log(staff, A.PRO_VERIFY, "pro", profile.user_id, profile.user)
    return profile


@transaction.atomic
def reject_pro(staff, profile: ProProfile, reason: str) -> ProProfile:
    """Refus ou retrait de la vérification : le pro voit le motif dans son espace."""
    _staff(staff)
    reason = _required(reason, "Indiquez ce qui manque au pro pour être vérifié.")
    profile.is_verified = False
    profile.verified_at = None
    profile.verification_note = reason[:300]
    profile.save(update_fields=["is_verified", "verified_at", "verification_note"])
    _withdraw_pending_quotes(profile.user)
    log(staff, A.PRO_REJECT, "pro", profile.user_id, profile.user, reason)
    return profile


def _target_type(user: User) -> str:
    return "pro" if user.is_pro else "client"


@transaction.atomic
def suspend_user(staff, user: User, reason: str) -> User:
    """Suspend un compte : plus de connexion possible, jetons révoqués, devis en attente retirés."""
    _staff(staff)
    reason = _required(reason, "Indiquez le motif de la suspension.")
    if user.is_staff or user.is_superuser:
        raise ValidationError("Un compte de l'équipe ne se suspend pas depuis la console.")
    if not user.is_active:
        raise ValidationError("Ce compte est déjà suspendu.")
    user.is_active = False
    user.suspension_reason = reason[:200]
    user.save(update_fields=["is_active", "suspension_reason"])
    Token.objects.filter(user=user).delete()  # déconnecté partout, tout de suite
    if user.is_pro:
        _withdraw_pending_quotes(user)
    log(staff, A.USER_SUSPEND, _target_type(user), user.pk, user, reason)
    return user


@transaction.atomic
def reactivate_user(staff, user: User) -> User:
    _staff(staff)
    if user.is_active:
        raise ValidationError("Ce compte est déjà actif.")
    user.is_active = True
    user.suspension_reason = ""
    user.save(update_fields=["is_active", "suspension_reason"])
    log(staff, A.USER_REACTIVATE, _target_type(user), user.pk, user)
    return user


# --- Demandes et litiges -------------------------------------------------------------------------


def cancel_request(staff, req: ServiceRequest, reason: str) -> ServiceRequest:
    req = jobs.staff_cancel(staff, req, reason)
    log(staff, A.REQUEST_CANCEL, "request", req.pk, f"#{req.pk} {req.title}", reason.strip())
    return req


@transaction.atomic
def set_staff_note(staff, req: ServiceRequest, note: str) -> ServiceRequest:
    _staff(staff)
    req.staff_note = note.strip()
    req.save(update_fields=["staff_note", "updated_at"])
    log(staff, A.REQUEST_NOTE, "request", req.pk, f"#{req.pk} {req.title}")
    return req


def open_dispute(staff, req: ServiceRequest, reason: str, description: str) -> Dispute:
    dispute = jobs.open_dispute(staff, req, reason, description)
    log(
        staff,
        A.DISPUTE_OPEN,
        "dispute",
        dispute.pk,
        f"Litige #{dispute.pk} · #{req.pk} {req.title}",
        dispute.get_reason_display(),
    )
    return dispute


def update_dispute(staff, dispute: Dispute, status: str, resolution: str) -> Dispute:
    dispute = jobs.update_dispute(staff, dispute, status, resolution)
    log(
        staff,
        A.DISPUTE_UPDATE,
        "dispute",
        dispute.pk,
        f"Litige #{dispute.pk} · #{dispute.request_id} {dispute.request.title}",
        f"{dispute.get_status_display()}{' : ' + dispute.resolution if dispute.is_closed else ''}",
    )
    return dispute


# --- Avis et messages ----------------------------------------------------------------------------


def _review_label(review: Review) -> str:
    pro = review.request.pro
    return f"Avis {review.rating}/5 sur {pro.get_full_name() if pro else 'un pro'}"


@transaction.atomic
def hide_review(staff, review: Review, reason: str) -> Review:
    _staff(staff)
    reason = _required(reason, "Indiquez pourquoi l'avis est masqué.")
    if review.is_hidden:
        raise ValidationError("Cet avis est déjà masqué.")
    review.is_hidden = True
    review.hidden_reason = reason[:200]
    review.save(update_fields=["is_hidden", "hidden_reason"])
    log(staff, A.REVIEW_HIDE, "review", review.pk, _review_label(review), reason)
    return review


@transaction.atomic
def show_review(staff, review: Review) -> Review:
    _staff(staff)
    if not review.is_hidden:
        raise ValidationError("Cet avis est déjà visible.")
    review.is_hidden = False
    review.hidden_reason = ""
    review.save(update_fields=["is_hidden", "hidden_reason"])
    log(staff, A.REVIEW_SHOW, "review", review.pk, _review_label(review))
    return review


@transaction.atomic
def set_contact_handled(staff, message: ContactMessage, handled: bool) -> ContactMessage:
    _staff(staff)
    if message.is_handled == handled:
        raise ValidationError("Rien à changer sur ce message.")
    message.is_handled = handled
    message.handled_at = timezone.now() if handled else None
    message.handled_by = staff if handled else None
    message.save(update_fields=["is_handled", "handled_at", "handled_by"])
    action = A.CONTACT_HANDLE if handled else A.CONTACT_REOPEN
    log(staff, action, "contact", message.pk, f"Message de {message.name}")
    return message
