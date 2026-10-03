"""Défi client contre le pompage de SMS (spec 001 S13, tâche 10).

Livré **désactivé** : ``OTP_CHALLENGE_REQUIRED = False``. Une fois activé (sans déploiement,
par variable d'environnement), ``otp/request`` exige un jeton vérifié par
``OTP_CHALLENGE_VERIFIER`` : Play Integrity ou App Attest sur mobile, Turnstile sur le web.
Les adaptateurs réels seront écrits quand la fraude l'exigera ; d'ici là, activer le drapeau
sans vérificateur refuse toutes les demandes (fermé, jamais ouvert).
"""

from collections.abc import Callable

from django.conf import settings
from django.utils.module_loading import import_string

from jeflink.common.errors import DomainError

# (jeton, app) -> True si le défi est réussi.
ChallengeVerifier = Callable[[str, str], bool]


def client_challenge_required() -> bool:
    return bool(settings.OTP_CHALLENGE_REQUIRED)


def check_client_challenge(*, token: str, app: str) -> None:
    """Ne fait rien si le drapeau est éteint ; sinon lève ``client_challenge_failed``."""
    if not client_challenge_required():
        return
    verifier_path = settings.OTP_CHALLENGE_VERIFIER
    if not token or not verifier_path:
        raise DomainError("client_challenge_failed", status=403)
    verifier: ChallengeVerifier = import_string(verifier_path)
    try:
        passed = verifier(token, app)
    except Exception as exc:
        raise DomainError("client_challenge_failed", status=403) from exc
    if not passed:
        raise DomainError("client_challenge_failed", status=403)
