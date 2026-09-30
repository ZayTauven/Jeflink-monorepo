"""Purge des données d'authentification (spec 001, « Rétention » ; tâche 18).

Lancée chaque jour par Celery beat (``accounts.tasks.purge_auth_data``). Relançable sans
danger : chaque étape est idempotente et travaille par lots, pour ne jamais tenir un verrou
longtemps. Les durées sont des réglages (``AUTH_RETENTION``), validées avec le consultant
juridique (Q8) : les changer ne touche pas le code.

Deux temps :
1. **clore** ce qui est échu mais encore ouvert (numéro en clair effacé tout de suite) ;
2. **supprimer** ce qui est clos depuis plus longtemps que sa durée de rétention.

``AuditEvent`` n'est pas concerné : il est en ajout seul (trigger en base), sa rétention de
5 ans relève d'un archivage dédié.
"""

import logging
from dataclasses import dataclass, field
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import Q, QuerySet
from django.utils import timezone

from .models import (
    DeviceSession,
    MfaChallenge,
    NoticeSms,
    OpsEnrollmentToken,
    OtpChallenge,
    OtpPhoneBlock,
    PhoneChangeRequest,
    RoleInvitation,
)

logger = logging.getLogger(__name__)
BATCH = 1000
# Un SMS d'information encore « en file » ou « en cours » après ce délai ne partira plus.
STUCK_NOTICE_AFTER = timedelta(hours=1)
OTP_BLOCK_GRACE = timedelta(hours=24)


@dataclass
class PurgeReport:
    counts: dict[str, int] = field(default_factory=dict)

    def add(self, name: str, count: int) -> None:
        self.counts[name] = self.counts.get(name, 0) + count


def _days(key: str) -> timedelta:
    return timedelta(days=settings.AUTH_RETENTION[key])


def _delete_in_batches(queryset: QuerySet) -> int:
    """Supprime par lots de ``BATCH`` (cascades comprises). Sûr à relancer."""
    total = 0
    model = queryset.model
    while True:
        ids = list(queryset.values_list("pk", flat=True)[:BATCH])
        if not ids:
            return total
        with transaction.atomic():
            model.objects.filter(pk__in=ids).delete()
        total += len(ids)


def _update_in_batches(queryset: QuerySet, **values) -> int:
    total = 0
    model = queryset.model
    while True:
        ids = list(queryset.values_list("pk", flat=True)[:BATCH])
        if not ids:
            return total
        with transaction.atomic():
            total += model.objects.filter(pk__in=ids).update(**values)


# --- 1. Clore ce qui est échu --------------------------------------------------------------------


def close_expired(now=None) -> PurgeReport:
    now = now or timezone.now()
    report = PurgeReport()
    report.add(
        "invitations_expired",
        _update_in_batches(
            RoleInvitation.objects.filter(
                status=RoleInvitation.Status.PENDING, expires_at__lte=now
            ),
            status=RoleInvitation.Status.EXPIRED,
            phone="",
            updated_at=now,
        ),
    )
    # Demandes de changement de numéro échues : nouveau numéro effacé, code en cours invalidé.
    expired_changes = PhoneChangeRequest.objects.filter(
        status__in=PhoneChangeRequest.OPEN, expires_at__lte=now
    )
    challenge_ids = list(
        expired_changes.exclude(challenge__isnull=True).values_list("challenge_id", flat=True)
    )
    report.add(
        "phone_changes_expired",
        _update_in_batches(
            expired_changes,
            status=PhoneChangeRequest.Status.EXPIRED,
            new_phone="",
            updated_at=now,
        ),
    )
    OtpChallenge.objects.filter(pk__in=challenge_ids, status=OtpChallenge.Status.PENDING).update(
        status=OtpChallenge.Status.EXPIRED, updated_at=now
    )
    report.add(
        "notices_stuck",
        _update_in_batches(
            NoticeSms.objects.filter(
                status__in=[NoticeSms.Status.QUEUED, NoticeSms.Status.SENDING],
                created_at__lte=now - STUCK_NOTICE_AFTER,
            ),
            status=NoticeSms.Status.UNKNOWN,
            error_code="stuck",
            phone="",
            updated_at=now,
        ),
    )
    return report


# --- 2. Supprimer au-delà de la rétention --------------------------------------------------------


def delete_expired(now=None) -> PurgeReport:
    now = now or timezone.now()
    report = PurgeReport()
    # Challenges OTP (et leurs envois, en cascade), y compris les challenges MFA qui en dépendent.
    report.add(
        "mfa_challenges",
        _delete_in_batches(MfaChallenge.objects.filter(expires_at__lte=now - _days("mfa"))),
    )
    report.add(
        "enrollment_tokens",
        _delete_in_batches(OpsEnrollmentToken.objects.filter(expires_at__lte=now - _days("mfa"))),
    )
    report.add(
        "otp_challenges",
        _delete_in_batches(OtpChallenge.objects.filter(created_at__lte=now - _days("otp"))),
    )
    report.add(
        "notices",
        _delete_in_batches(
            NoticeSms.objects.filter(created_at__lte=now - _days("otp")).exclude(
                status__in=[NoticeSms.Status.QUEUED, NoticeSms.Status.SENDING]
            )
        ),
    )
    report.add(
        "invitations",
        _delete_in_batches(
            RoleInvitation.objects.exclude(status=RoleInvitation.Status.PENDING).filter(
                updated_at__lte=now - _days("closed_requests")
            )
        ),
    )
    report.add(
        "phone_changes",
        _delete_in_batches(
            PhoneChangeRequest.objects.exclude(status__in=PhoneChangeRequest.OPEN).filter(
                updated_at__lte=now - _days("closed_requests")
            )
        ),
    )
    # Sessions révoquées ou expirées : les refresh retirés partent avec elles (cascade).
    horizon = now - _days("sessions")
    report.add(
        "sessions",
        _delete_in_batches(
            DeviceSession.objects.filter(
                Q(revoked_at__lte=horizon)
                | Q(revoked_at__isnull=True, idle_expires_at__lte=horizon)
                | Q(revoked_at__isnull=True, absolute_expires_at__lte=horizon)
            )
        ),
    )
    report.add(
        "otp_phone_blocks",
        _delete_in_batches(OtpPhoneBlock.objects.filter(blocked_until__lte=now - OTP_BLOCK_GRACE)),
    )
    return report


def purge_auth_data(now=None) -> dict[str, int]:
    """Clôture puis suppression. Renvoie les volumes (jamais de donnée personnelle)."""
    report = close_expired(now)
    deleted = delete_expired(now)
    counts = {**report.counts, **deleted.counts}
    logger.info("purge_auth_data %s", " ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    return counts
