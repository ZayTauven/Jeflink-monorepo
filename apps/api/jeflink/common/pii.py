"""Données personnelles : masquage, pseudonymisation, filtrage (règle 8, spec 001 S14 et S15).

Tout numéro qui doit être tracé (audit, compteurs, blocages) l'est sous forme ``mask_phone()``
pour la lecture humaine et ``phone_hmac()`` pour les rapprochements, jamais en clair.
"""

import hashlib
import hmac
import re
from collections.abc import Mapping
from typing import Any

from django.conf import settings

REDACTED = "[filtré]"

# Clés dont la valeur n'apparaît jamais dans un journal, une métadonnée d'audit ou Sentry.
SENSITIVE_KEYS = frozenset(
    {
        "phone",
        "new_phone",
        "code",
        "refresh",
        "access",
        "mfa_token",
        "challenge_secret",
        "secret",
        "otpauth_uri",
        "enrollment_token",
        "authorization",
        "cookie",
        "password",
        "token",
        "jf_at",
        "jf_rt",
        "jf_mfa",
    }
)

_E164 = re.compile(r"\+[1-9]\d{7,14}")
# Formats sénégalais tels que saisis : 77 123 45 67, 771234567, 00221 77…, +221 77…
_SN_NATIONAL = re.compile(r"(?:(?:00221|\+?221)\s*|(?<!\d))7[05-8](?:[\s.-]?\d){7}(?!\d)")
_KEYS_ALTERNATION = "|".join(sorted(SENSITIVE_KEYS, key=len, reverse=True))
_KEY_VALUE = re.compile(
    rf"""(?P<key>(?<![\w-])["']?(?:{_KEYS_ALTERNATION})["']?\s*[:=]\s*)"""
    r"""(?P<value>"[^"]*"|'[^']*'|(?:Bearer|Basic|Token)\s+[^\s,&;}\]]+|[^\s,&;}\]]+)""",
    re.IGNORECASE,
)


def mask_phone(e164: str) -> str:
    """``+221771234567`` → ``+221 •••••••67`` : indicatif et deux derniers chiffres."""
    if not e164 or not e164.startswith("+") or len(e164) < 6:
        return "•••"
    country_len = 4 if e164.startswith("+221") else 3
    hidden = len(e164) - country_len - 2
    return f"{e164[:country_len]} {'•' * hidden}{e164[-2:]}"


def phone_hmac(e164: str) -> str:
    """Pseudonyme stable d'un numéro (HMAC-SHA256, clé ``PII_HMAC_KEY``)."""
    key = settings.PII_HMAC_KEY.encode()
    return hmac.new(key, e164.encode(), hashlib.sha256).hexdigest()


def redact(text: str) -> str:
    """Masque numéros et valeurs de clés sensibles dans un texte libre."""
    if not text:
        return text
    text = _KEY_VALUE.sub(lambda m: f"{m.group('key')}{REDACTED}", text)
    text = _E164.sub(REDACTED, text)
    return _SN_NATIONAL.sub(REDACTED, text)


def contains_pii(text: str) -> bool:
    return redact(text) != text


def redact_data(value: Any) -> Any:
    """Version récursive de ``redact`` pour dictionnaires et listes (Sentry, métadonnées)."""
    if isinstance(value, Mapping):
        return {
            k: REDACTED if str(k).lower() in SENSITIVE_KEYS else redact_data(v)
            for k, v in value.items()
        }
    if isinstance(value, list | tuple):
        return type(value)(redact_data(v) for v in value)
    if isinstance(value, str):
        return redact(value)
    return value
