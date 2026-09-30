"""Point d'entrée unique : ``get_sms_gateway()`` renvoie l'adaptateur choisi par ``SMS_GATEWAY``."""

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from .base import (
    SmsAmbiguousError,
    SmsError,
    SmsGateway,
    SmsPermanentError,
    SmsResult,
    SmsTransientError,
)

__all__ = [
    "SmsAmbiguousError",
    "SmsError",
    "SmsGateway",
    "SmsPermanentError",
    "SmsResult",
    "SmsTransientError",
    "check_sms_settings",
    "get_sms_gateway",
]

FAKE_ALLOWED_ENVS = frozenset({"local", "test"})


def check_sms_settings() -> None:
    """Appelée au démarrage : refuse un adaptateur inconnu, ou ``fake`` hors local/test (S23)."""
    name = settings.SMS_GATEWAY
    if name == "fake" and settings.DJANGO_ENV not in FAKE_ALLOWED_ENVS:
        raise ImproperlyConfigured(
            f"SMS_GATEWAY=fake interdit avec DJANGO_ENV={settings.DJANGO_ENV}."
        )
    if name and name not in _registry():
        raise ImproperlyConfigured(f"SMS_GATEWAY inconnu : {name}.")


def get_sms_gateway() -> SmsGateway:
    check_sms_settings()
    name = settings.SMS_GATEWAY
    if not name:
        raise ImproperlyConfigured("SMS_GATEWAY n'est pas configuré.")
    return _registry()[name]()


def _registry() -> dict[str, type[SmsGateway]]:
    from .fake import FakeSmsGateway

    # Les adaptateurs de fournisseurs réels s'ajoutent ici (tâche api 20, après Q7).
    return {"fake": FakeSmsGateway}
