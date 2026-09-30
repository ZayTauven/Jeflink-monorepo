"""Gabarits SMS de l'OTP (spec 001, « Gabarits SMS » ; ADR 0008 ; S13).

- GSM-7, un seul SMS (160 caractères au plus), testés pour chaque app et chaque langue.
- **Aucune donnée fournie par un utilisateur** : seulement le code, le hachage de l'app
  (SMS Retriever Android) et la ligne WebOTP.
- ``wo`` se replie sur ``fr`` tant que la traduction n'est pas validée (Q12).
"""

from django.conf import settings
from django.utils import translation
from django.utils.translation import gettext as _

from jeflink.common.gsm7 import is_gsm7, segments


def _login_sentence(app: str, code: str) -> str:
    if app == "pro":
        return _(
            "Jeflink Pro : votre code de connexion est %(code)s. Valable 10 min. "
            "Ne le donnez à personne, ni à un client, ni à Jeflink."
        ) % {"code": code}
    return _(
        "Jeflink : votre code de connexion est %(code)s. Valable 10 min. "
        "Ne le donnez à personne, ni à un artisan, ni à Jeflink."
    ) % {"code": code}


def _purpose_sentence(purpose: str, code: str) -> str:
    if purpose == "delete_account":
        return _(
            "Jeflink : code %(code)s pour SUPPRIMER votre compte. Si ce n'est pas vous, "
            "ignorez ce SMS. Ne le donnez à personne."
        ) % {"code": code}
    if purpose == "change_phone":
        return _(
            "Jeflink : code %(code)s pour relier ce numéro à votre compte. "
            "Ne le donnez à personne, ni à Jeflink."
        ) % {"code": code}
    return _("Jeflink : votre code est %(code)s. Ne le donnez à personne.") % {"code": code}


def otp_sms_body(*, app: str, purpose: str, code: str, language: str = "fr") -> str:
    """Texte complet du SMS. Lève ValueError si le résultat sort du GSM-7 ou d'un SMS."""
    with translation.override(language if language in {"fr", "wo"} else "fr"):
        sentence = (
            _login_sentence(app, code) if purpose == "login" else _purpose_sentence(purpose, code)
        )
    lines = [sentence]
    app_hash = settings.SMS_ANDROID_APP_HASH.get(app, "")
    if app_hash:
        lines.append(app_hash)
    if app in {"web", "console"}:
        lines.append(f"@{settings.WEBOTP_DOMAIN} #{code}")
    body = "\n".join(lines)
    if not is_gsm7(body) or segments(body) != 1:
        raise ValueError("gabarit SMS hors GSM-7 ou plus long qu'un SMS")
    return body
