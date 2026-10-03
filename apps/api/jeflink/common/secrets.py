"""Contrôle des secrets applicatifs au démarrage (spec 001 S21) : on refuse de démarrer plutôt
que de tourner avec une clé absente, courte, réutilisée ou publique. Les valeurs ne sont
jamais affichées."""

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

MIN_BYTES = 32
# Marqueurs des valeurs publiques de docker-compose et de settings/test.py.
PUBLIC_VALUE_MARKERS = ("not-secret", "test-", "dGVzdC1", "bG9jYWwt")
NON_PROD_ENVS = frozenset({"local", "test"})


def _named_secrets() -> list[tuple[str, str]]:
    named = [(f"JWT_SIGNING_KEYS[{kid}]", key) for kid, key in settings.JWT_SIGNING_KEYS.items()]
    named += [("OTP_HMAC_KEY", settings.OTP_HMAC_KEY), ("PII_HMAC_KEY", settings.PII_HMAC_KEY)]
    named += [(f"MFA_ENCRYPTION_KEYS[{i}]", k) for i, k in enumerate(settings.MFA_ENCRYPTION_KEYS)]
    named += [
        (f"DATA_ENCRYPTION_KEYS[{i}]", k) for i, k in enumerate(settings.DATA_ENCRYPTION_KEYS)
    ]
    named += [(f"BFF_SHARED_SECRETS[{i}]", k) for i, k in enumerate(settings.BFF_SHARED_SECRETS)]
    return named


def _fernet_problems() -> list[str]:
    from cryptography.fernet import Fernet

    problems = []
    for setting in ("MFA_ENCRYPTION_KEYS", "DATA_ENCRYPTION_KEYS"):
        for i, key in enumerate(getattr(settings, setting)):
            try:
                Fernet(key)
            except (ValueError, TypeError):
                problems.append(f"{setting}[{i}] : clé Fernet invalide")
    return problems


def _storage_problems() -> list[str]:
    """Stockage d'objets (ADR 0011) : hors local et test, point d'accès, bucket et identifiants
    sont obligatoires, l'hôte public est en HTTPS et les identifiants ne sont pas ceux de dev."""
    if settings.DJANGO_ENV in NON_PROD_ENVS:
        return []
    problems = []
    for name in (
        "S3_ENDPOINT",
        "S3_PUBLIC_ENDPOINT",
        "S3_BUCKET",
        "S3_ACCESS_KEY",
        "S3_SECRET_KEY",
    ):
        if not getattr(settings, name):
            problems.append(f"{name} : absent")
    if settings.S3_PUBLIC_ENDPOINT and not settings.S3_PUBLIC_ENDPOINT.startswith("https://"):
        problems.append("S3_PUBLIC_ENDPOINT : HTTPS obligatoire")
    for name in ("S3_ACCESS_KEY", "S3_SECRET_KEY"):
        if any(marker in getattr(settings, name) for marker in PUBLIC_VALUE_MARKERS):
            problems.append(f"{name} : valeur publique de dev ou de test interdite ici")
    return problems


def secret_problems() -> list[str]:
    problems = _storage_problems()
    if settings.DJANGO_ENV not in settings.DJANGO_ENVS:
        problems.append("DJANGO_ENV : valeur inconnue")
    if len(settings.SECRET_KEY.encode()) < MIN_BYTES:
        problems.append(f"SECRET_KEY : trop courte (< {MIN_BYTES} octets)")
    for setting, present in (
        ("JWT_SIGNING_KEYS", settings.JWT_SIGNING_KEYS),
        ("MFA_ENCRYPTION_KEYS", settings.MFA_ENCRYPTION_KEYS),
        ("DATA_ENCRYPTION_KEYS", settings.DATA_ENCRYPTION_KEYS),
        ("BFF_SHARED_SECRETS", settings.BFF_SHARED_SECRETS),
    ):
        if not present:
            problems.append(f"{setting} : aucune valeur")
    raw_kids = [item.split(":", 1)[0] for item in settings.JWT_SIGNING_KEYS_RAW]
    if len(raw_kids) != len(set(raw_kids)) or len(raw_kids) != len(settings.JWT_SIGNING_KEYS):
        problems.append("JWT_SIGNING_KEYS : kid en double ou entrée sans « kid: »")
    named = _named_secrets()
    for name, value in named:
        if len(value.encode()) < MIN_BYTES:
            problems.append(f"{name} : absent ou trop court (< {MIN_BYTES} octets)")
    if settings.DJANGO_ENV not in NON_PROD_ENVS:
        for name, value in [("SECRET_KEY", settings.SECRET_KEY), *named]:
            if any(marker in value for marker in PUBLIC_VALUE_MARKERS):
                problems.append(f"{name} : valeur publique de dev ou de test interdite ici")
    seen: dict[str, str] = {}
    for name, value in named:
        if not value:
            continue
        if value == settings.SECRET_KEY:
            problems.append(f"{name} : identique à SECRET_KEY")
        if value in seen:
            problems.append(f"{name} : identique à {seen[value]}")
        seen.setdefault(value, name)
    return problems + _fernet_problems()


def check_secrets() -> None:
    problems = secret_problems()
    if problems:
        raise ImproperlyConfigured("Secrets invalides :\n  " + "\n  ".join(problems))
