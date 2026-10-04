"""Chiffrement des données sensibles au repos (``DATA_ENCRYPTION_KEYS``, MultiFernet).

La première clé chiffre, toutes déchiffrent : la rotation ajoute une clé en tête. Distinct des clés
du second facteur (``MFA_ENCRYPTION_KEYS``). Aujourd'hui : le code de fin de mission.
"""

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from django.conf import settings


def _fernet() -> MultiFernet:
    return MultiFernet([Fernet(key) for key in settings.DATA_ENCRYPTION_KEYS])


def encrypt(plain: str) -> str:
    return _fernet().encrypt(plain.encode()).decode()


def decrypt(token: str) -> str | None:
    """Le texte clair, ou ``None`` si le jeton est vide ou ne se déchiffre plus (clé retirée)."""
    if not token:
        return None
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken:
        return None
