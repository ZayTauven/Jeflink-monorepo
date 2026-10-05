"""Validation des textes saisis par l'Ops et publiés tels quels (spec 006).

Un texte publié ne doit mener nulle part hors de Jeflink : ni numéro (portable ou fixe), ni lien,
ni nom de domaine, ni pseudo de réseau social. Les faux positifs sont préférés aux trous : l'Ops
reformule (une espace après le point suffit).
"""

import re

from django.core.exceptions import ValidationError

from .pii import contains_pii

_EDGE_BEFORE = r"(?<![0-9A-Za-z])"
_EDGE_AFTER = r"(?![0-9A-Za-z])"
# Fixes du Sénégal (33 et 30 + 7 chiffres), avec ou sans indicatif et séparateurs.
_LANDLINE = re.compile(
    rf"(?:{_EDGE_BEFORE}(?:00221|\+221|221)[\s.-]?|{_EDGE_BEFORE})3[03](?:[\s.-]?\d){{7}}{_EDGE_AFTER}"
)
# Domaine : extension en minuscules (« plombier.shop »), ou extension connue quelle que soit la
# casse (« Site.COM »). « M.Diop » et « etc. » ne sont pas pris pour un domaine.
_DOMAIN_LOWER = re.compile(r"[\w-]+\.[a-z]{2,}\b")
_SCHEME = re.compile(r"https?://|www\.", re.IGNORECASE)
_KNOWN_TLD = re.compile(
    r"[\w-]+\.(?:com|net|org|info|biz|io|me|ly|co|app|sn|fr|shop|xyz|link)\b", re.IGNORECASE
)
# Pseudo ou e-mail : « @plombier_ouakam ».
_HANDLE = re.compile(r"@\w")


def validate_public_text(value: str) -> None:
    """Refuse un numéro de téléphone, une URL ou un domaine, un pseudo ``@xxx``.

    Le texte sera publié sur le site public : un numéro y serait lu par tout le monde, et un lien
    mènerait hors de Jeflink.
    """
    if contains_pii(value) or _LANDLINE.search(value):
        raise ValidationError(
            "Un numéro de téléphone ne peut pas figurer ici.", code="contains_phone"
        )
    if _SCHEME.search(value) or _DOMAIN_LOWER.search(value) or _KNOWN_TLD.search(value):
        raise ValidationError(
            "Un lien ou un nom de domaine ne peut pas figurer ici "
            "(mettez une espace après le point).",
            code="contains_url",
        )
    if _HANDLE.search(value):
        raise ValidationError("Un pseudo (@…) ne peut pas figurer ici.", code="contains_handle")
