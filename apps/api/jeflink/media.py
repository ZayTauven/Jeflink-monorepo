"""Images envoyées par les utilisateurs (photos de profil, images des métiers…).

Chaque image est vérifiée (vraie image, 8 Mo au plus), redressée selon l'orientation du
téléphone, débarrassée de ses métadonnées (la position GPS d'une photo prise à la maison),
réduite et convertie en WebP : léger pour les forfaits mobiles. Stockage local (MEDIA_ROOT) pour
la démo ; voir ARCHITECTURE.md › Après la démo pour la production.
"""

import re
from contextlib import suppress
from io import BytesIO
from uuid import uuid4

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from PIL import Image, ImageOps
from rest_framework.exceptions import ValidationError

MAX_BYTES = 8 * 1024 * 1024
# Une photo de téléphone fait 12 à 48 Mpx. Au-delà de 24 Mpx, refusée avant décodage : un PNG
# de quelques Ko peut sinon occuper des centaines de Mo (« bombe de décompression »).
MAX_PIXELS = 24_000_000
Image.MAX_IMAGE_PIXELS = MAX_PIXELS  # filet de sécurité de Pillow (il ne lève qu'au double)
FORMATS = ("JPEG", "PNG", "WEBP")  # pas de TIFF, PSD, EPS… : moins de décodeurs exposés
NAME = re.compile(r"[0-9a-f]{32}.webp")

NOT_AN_IMAGE = "Ce fichier n'est pas une image lisible (photo JPEG, PNG ou WebP)."


def save_image(upload, folder: str, field: str = "photo", max_side: int = 1600) -> str:
    """Enregistre l'image et renvoie son adresse publique (/media/<dossier>/<nom>.webp)."""
    if upload is None:
        raise ValidationError({field: "Choisissez une image."})
    if upload.size > MAX_BYTES:
        raise ValidationError({field: "Image trop lourde : 8 Mo au plus."})
    try:
        with Image.open(upload, formats=FORMATS) as probe:
            probe.verify()  # fichier tronqué ou déguisé : refusé
        upload.seek(0)
        with Image.open(upload, formats=FORMATS) as original:
            if original.width * original.height > MAX_PIXELS:
                raise ValidationError({field: "Image trop grande : 24 millions de pixels au plus."})
            original.thumbnail((max_side, max_side))  # réduite d'abord (JPEG : décodage réduit)
            image = ImageOps.exif_transpose(original)  # redressée, comme sur le téléphone
            has_alpha = "A" in image.getbands()
            image = image.convert("RGBA" if has_alpha else "RGB")
            out = BytesIO()
            # Aucune métadonnée transmise : l'EXIF (GPS, appareil, date) n'est pas recopié.
            image.save(out, "WEBP", quality=80, method=4)
    except ValidationError:
        raise
    except Exception as exc:
        # Fichier déguisé, tronqué ou EXIF malformé (KeyError, struct.error…) : jamais une 500.
        raise ValidationError({field: NOT_AN_IMAGE}) from exc
    path = default_storage.save(f"{folder}/{uuid4().hex}.webp", ContentFile(out.getvalue()))
    return f"{settings.MEDIA_URL}{path}"


def is_uploaded(url: str, folder: str) -> bool:
    """Adresse d'une image envoyée dans `folder` (nom tiré par save_image, rien d'autre)."""
    prefix = f"{settings.MEDIA_URL}{folder}/"
    return url.startswith(prefix) and bool(NAME.fullmatch(url.removeprefix(prefix)))


def delete_image(url: str, folder: str) -> None:
    """Supprime une image envoyée dans `folder` ; les images du site (/images/…) et toute autre
    adresse restent (une photo de profil ne peut pas être effacée via l'image d'un métier)."""
    if is_uploaded(url, folder):
        with suppress(OSError):
            default_storage.delete(url.removeprefix(settings.MEDIA_URL))
