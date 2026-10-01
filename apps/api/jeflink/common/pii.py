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
# Comparées après normalisation : minuscules, « - » → « _ », préfixe HTTP_ retiré.
SENSITIVE_KEYS = frozenset(
    {
        "phone",
        "new_phone",
        "code",
        "otp_code",
        "refresh",
        "access",
        "mfa_token",
        "challenge_secret",
        "secret",
        "otpauth_uri",
        "enrollment_token",
        "authorization",
        "cookie",
        "set_cookie",
        "password",
        "token",
        "jf_at",
        "jf_rt",
        "jf_mfa",
        "sessionid",
        "csrftoken",
        "csrfmiddlewaretoken",
        "idempotency_key",
        "install_id",
    }
)
# Toute en-tête interne X-Jeflink-* (secret BFF, IP cliente…).
_SENSITIVE_PREFIXES = ("x_jeflink_",)
# Valeurs qui s'étendent jusqu'à la fin de la ligne (plusieurs cookies, schéma + jeton).
_WHOLE_LINE_KEYS = ("authorization", "cookie", "set_cookie")

# Pas de chiffre ni de lettre collés avant/après : évite les faux positifs dans un HMAC ou un UUID.
_EDGE_BEFORE = r"(?<![0-9A-Za-z])"
_EDGE_AFTER = r"(?![0-9A-Za-z])"
# International, avec ou sans séparateurs : +221771234567, +33 6 12 34 56 78.
_INTERNATIONAL = re.compile(rf"\+[1-9](?:[\s.-]?\d){{7,14}}{_EDGE_AFTER}")
# Sénégal tel que saisi : 77 123 45 67, 771234567, 00221 77…, 221 77…, plages 7x récentes.
_SN_NATIONAL = re.compile(
    rf"(?:{_EDGE_BEFORE}(?:00221|221)[\s.-]?|{_EDGE_BEFORE})7\d(?:[\s.-]?\d){{7}}{_EDGE_AFTER}"
)
_JWT = re.compile(r"eyJ[\w-]+\.[\w-]+\.[\w-]+")
# Jetons opaques Jeflink : refresh (jfr_), MFA (jfm_), enrôlement TOTP (jfe_).
_OPAQUE_TOKEN = re.compile(r"(?<![\w-])jf[rme]_[\w-]{20,}")


def _key_pattern(keys: tuple[str, ...]) -> str:
    variants = sorted((k.replace("_", "[-_]") for k in keys), key=len, reverse=True)
    return "|".join(variants)


_KEY_PREFIX = r"""(?<![\w-])["']?(?:HTTP_)?"""
_ALREADY = rf"(?!{re.escape(REDACTED)})"
_WHOLE_LINE = re.compile(
    rf"""(?P<key>{_KEY_PREFIX}(?:{_key_pattern(_WHOLE_LINE_KEYS)})["']?\s*[:=]\s*)"""
    r"""(?P<value>"[^"]*"|'[^']*'|[^\r\n]+)""",
    re.IGNORECASE,
)
_KEY_VALUE = re.compile(
    rf"""(?P<key>{_KEY_PREFIX}(?:{_key_pattern(tuple(SENSITIVE_KEYS))}|x[-_]jeflink[-_][\w-]+)"""
    rf"""["']?\s*[:=]\s*){_ALREADY}"""
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


MASKED_PHONE_RE = re.compile(r"^\+\d{2,3} •{5,13}\d{2}$")
PHONE_HMAC_RE = re.compile(r"^[0-9a-f]{64}$")


def phone_hmac(e164: str) -> str:
    """Pseudonyme stable d'un numéro (HMAC-SHA256, clé ``PII_HMAC_KEY``)."""
    key = settings.PII_HMAC_KEY.encode()
    return hmac.new(key, e164.encode(), hashlib.sha256).hexdigest()


def _replace_value(match: re.Match[str]) -> str:
    return f"{match.group('key')}{REDACTED}"


def redact(text: str) -> str:
    """Masque numéros, jetons et valeurs de clés sensibles dans un texte libre."""
    if not text:
        return text
    text = _WHOLE_LINE.sub(_replace_value, text)
    text = _KEY_VALUE.sub(_replace_value, text)
    text = _JWT.sub(REDACTED, text)
    text = _OPAQUE_TOKEN.sub(REDACTED, text)
    text = _INTERNATIONAL.sub(REDACTED, text)
    return _SN_NATIONAL.sub(REDACTED, text)


def contains_pii(text: str) -> bool:
    return redact(text) != text


def is_sensitive_key(key: object) -> bool:
    normalized = str(key).lower().replace("-", "_").removeprefix("http_")
    return normalized in SENSITIVE_KEYS or normalized.startswith(_SENSITIVE_PREFIXES)


def redact_data(value: Any) -> Any:
    """Version récursive de ``redact`` pour dictionnaires et listes (Sentry, métadonnées)."""
    if isinstance(value, Mapping):
        return {k: REDACTED if is_sensitive_key(k) else redact_data(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return type(value)(redact_data(v) for v in value)
    if isinstance(value, str):
        return redact(value)
    return value
