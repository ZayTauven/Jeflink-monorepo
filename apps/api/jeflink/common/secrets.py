"""Contrôle des secrets applicatifs au démarrage (spec 001 S21) : on refuse de démarrer plutôt
que de tourner avec une clé absente, courte ou réutilisée. Les valeurs ne sont jamais affichées."""

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

MIN_BYTES = 32


def _named_secrets() -> list[tuple[str, str]]:
    named = [(f"JWT_SIGNING_KEYS[{kid}]", key) for kid, key in settings.JWT_SIGNING_KEYS.items()]
    named += [("OTP_HMAC_KEY", settings.OTP_HMAC_KEY), ("PII_HMAC_KEY", settings.PII_HMAC_KEY)]
    named += [(f"MFA_ENCRYPTION_KEYS[{i}]", k) for i, k in enumerate(settings.MFA_ENCRYPTION_KEYS)]
    named += [(f"BFF_SHARED_SECRETS[{i}]", k) for i, k in enumerate(settings.BFF_SHARED_SECRETS)]
    return named


def secret_problems() -> list[str]:
    problems = []
    for setting, present in (
        ("JWT_SIGNING_KEYS", settings.JWT_SIGNING_KEYS),
        ("MFA_ENCRYPTION_KEYS", settings.MFA_ENCRYPTION_KEYS),
        ("BFF_SHARED_SECRETS", settings.BFF_SHARED_SECRETS),
    ):
        if not present:
            problems.append(f"{setting} : aucune valeur")
    named = _named_secrets()
    for name, value in named:
        if len(value.encode()) < MIN_BYTES:
            problems.append(f"{name} : absent ou trop court (< {MIN_BYTES} octets)")
    seen: dict[str, str] = {}
    for name, value in named:
        if not value:
            continue
        if value == settings.SECRET_KEY:
            problems.append(f"{name} : identique à SECRET_KEY")
        if value in seen:
            problems.append(f"{name} : identique à {seen[value]}")
        seen.setdefault(value, name)
    return problems


def check_secrets() -> None:
    problems = secret_problems()
    if problems:
        raise ImproperlyConfigured("Secrets invalides :\n  " + "\n  ".join(problems))
