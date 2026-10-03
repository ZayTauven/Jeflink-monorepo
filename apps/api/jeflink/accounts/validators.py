import re
import unicodedata

from jeflink.common.errors import DomainError
from jeflink.common.pii import contains_pii

_URL = re.compile(r"(https?://|www\.|\b[\w-]+\.(com|sn|fr|net|org|io|app)\b)", re.IGNORECASE)
# Termes réservés cherchés en sous-chaîne dans la forme de comparaison (S26, I8).
_RESERVED_SUBSTRINGS = ("jeflink", "support", "admin", "moderat", "equipejef")
# « ops » est trop court pour une sous-chaîne (Hopson…) : on l'exige comme mot entier.
_RESERVED_WORDS = re.compile(r"\bops\b")
# Homoglyphes courants (grec, cyrillique, chiffres) ramenés à leur lettre latine.
_HOMOGLYPHS = str.maketrans(
    {
        "α": "a", "а": "a", "ο": "o", "о": "o", "ε": "e", "е": "e", "ѕ": "s", "і": "i",
        "ι": "i", "ј": "j", "р": "p", "ρ": "p", "с": "c", "ϲ": "c", "κ": "k", "к": "k",
        "ν": "v", "т": "t", "у": "y", "х": "x", "м": "m", "н": "h", "в": "b", "ℓ": "l",
        "0": "o", "1": "l", "3": "e", "4": "a", "5": "s", "7": "t", "@": "a", "$": "s",
    }
)  # fmt: skip
_FORBIDDEN_CATEGORIES = {"Cc", "Cf", "Co", "Cn", "Cs"}


def comparison_form(name: str) -> str:
    """Forme de comparaison : NFKC, casse repliée, sans diacritiques, homoglyphes ramenés."""
    folded = unicodedata.normalize("NFKC", name).casefold()
    stripped = "".join(
        ch for ch in unicodedata.normalize("NFKD", folded) if not unicodedata.combining(ch)
    )
    return stripped.translate(_HOMOGLYPHS)


def clean_display_name(raw: str) -> str:
    """Nom affiché : 2 à 80 caractères, sans contrôle, bidi, URL, numéro ni terme réservé."""
    name = unicodedata.normalize("NFC", " ".join((raw or "").split()))
    if not 2 <= len(name) <= 80:
        raise DomainError("display_name_length")
    if any(unicodedata.category(ch) in _FORBIDDEN_CATEGORIES for ch in name):
        raise DomainError("display_name_invalid")
    if _URL.search(name) or contains_pii(name):
        raise DomainError("display_name_reserved")
    form = comparison_form(name)
    letters_only = "".join(ch for ch in form if ch.isalpha())
    if any(term in letters_only for term in _RESERVED_SUBSTRINGS) or _RESERVED_WORDS.search(form):
        raise DomainError("display_name_reserved")
    return name
