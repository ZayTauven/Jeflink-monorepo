import re
import unicodedata

from jeflink.common.errors import DomainError

_URL = re.compile(r"(https?://|www\.|\b[\w-]+\.(com|sn|fr|net|org|io|app)\b)", re.IGNORECASE)
# Termes qui permettraient d'usurper l'équipe (S26).
_RESERVED = re.compile(
    r"\b(jeflink|support|admin|administrateur|ops|moderateur|modérateur)\b", re.I
)


def clean_display_name(raw: str) -> str:
    """Nom affiché : 2 à 80 caractères, sans contrôle, bidi, URL ni terme réservé (S26)."""
    name = unicodedata.normalize("NFC", " ".join((raw or "").split()))
    if not 2 <= len(name) <= 80:
        raise DomainError("display_name_length")
    # Cc : caractères de contrôle ; Cf : formatage (bidi, largeur nulle…).
    if any(unicodedata.category(ch) in {"Cc", "Cf"} for ch in name):
        raise DomainError("display_name_invalid")
    if _URL.search(name) or _RESERVED.search(name):
        raise DomainError("display_name_reserved")
    return name
