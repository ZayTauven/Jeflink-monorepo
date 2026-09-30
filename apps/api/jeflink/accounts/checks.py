"""Vérifications Django du compte de revue des stores (S17).

- ``review_settings`` (sans base) : fenêtre bien formée et bornée (45 jours au plus hors
  local/test), numéros valides et dans les régions OTP autorisées ;
- ``review_accounts`` (tag ``database``) : aucun numéro de ``OTP_REVIEW_ACCOUNTS`` ne
  correspond à un compte réel non marqué. À lancer au déploiement : ``manage.py check
  --database default --deploy`` refuse alors de démarrer.

Défense à l'exécution en plus : le code de revue n'est accepté que pour un compte marqué.
"""

from datetime import timedelta

from django.conf import settings
from django.core.checks import Error, Tags, register
from django.utils import timezone

from jeflink.common.errors import DomainError


@register()
def review_settings(app_configs, **kwargs) -> list[Error]:
    from .phone import normalize_phone, phone_region
    from .review_accounts import review_until

    errors = []
    try:
        until = review_until()
    except ValueError:
        return [Error("OTP_REVIEW_ENABLED_UNTIL : date ISO 8601 invalide.", id="accounts.E101")]
    if (
        until is not None
        and settings.DJANGO_ENV not in {"local", "test"}
        and until > timezone.now() + timedelta(days=settings.OTP_REVIEW_MAX_DAYS)
    ):
        errors.append(
            Error(
                f"OTP_REVIEW_ENABLED_UNTIL : au plus {settings.OTP_REVIEW_MAX_DAYS} jours.",
                id="accounts.E102",
            )
        )
    for index, raw in enumerate(settings.OTP_REVIEW_ACCOUNTS):
        try:
            phone = normalize_phone(raw)
        except DomainError:
            errors.append(Error(f"OTP_REVIEW_ACCOUNTS[{index}] : invalide.", id="accounts.E103"))
            continue
        if phone_region(phone) not in settings.OTP_ALLOWED_REGIONS:
            errors.append(
                Error(f"OTP_REVIEW_ACCOUNTS[{index}] : région non autorisée.", id="accounts.E104")
            )
    return errors


@register(Tags.database)
def review_accounts(app_configs, databases=None, **kwargs) -> list[Error]:
    if not databases or "default" not in databases:
        return []
    from .models import User
    from .review_accounts import review_phones

    try:
        phones = review_phones()
    except DomainError:
        return []  # signalé par review_settings
    real = User.objects.filter(phone__in=phones, is_review_account=False).count()
    if real:
        return [
            Error(
                "OTP_REVIEW_ACCOUNTS : un numéro correspond à un compte réel non marqué.",
                id="accounts.E105",
            )
        ]
    return []
