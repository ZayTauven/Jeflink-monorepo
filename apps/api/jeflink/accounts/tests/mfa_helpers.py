"""Aides communes aux tests du second facteur Ops (TOTP)."""

from datetime import timedelta

import pyotp
from django.utils import timezone

from jeflink.accounts.mfa import TOTP_DIGITS, TOTP_INTERVAL, _fernet
from jeflink.accounts.models import TotpDevice


def enroll(user, *, locked: bool = False) -> pyotp.TOTP:
    """TOTP confirmé pour ``user`` ; renvoie le générateur de codes de son application."""
    secret = pyotp.random_base32(length=32)
    TotpDevice.objects.create(
        user=user,
        secret_encrypted=_fernet().encrypt(secret.encode()).decode(),
        # Enrôlé de longue date : antérieur aux sessions ouvertes par les tests.
        confirmed_at=timezone.now() - timedelta(days=1),
        locked_at=timezone.now() if locked else None,
    )
    return pyotp.TOTP(secret, digits=TOTP_DIGITS, interval=TOTP_INTERVAL)
