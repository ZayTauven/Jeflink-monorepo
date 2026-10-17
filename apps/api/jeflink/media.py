"""Images envoyées par les utilisateurs (photos de profil, images des métiers…).

Chaque image est vérifiée (vraie image, 8 Mo au plus), redressée selon l'orientation du
téléphone, débarrassée de ses métadonnées (la position GPS d'une photo prise à la maison),
réduite et convertie en WebP : léger pour les forfaits mobiles. Stockage local (MEDIA_ROOT) pour
la démo ; voir ARCHITECTURE.md › Après la démo pour la production.
"""

from contextlib import suppress
from io import BytesIO
from uuid import uuid4

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from PIL import Image, ImageOps, UnidentifiedImageError
from rest_framework.exceptions import ValidationError

MAX_BYTES = 8 * 1024 * 1024
# Au-delà, Pillow refuse l'image (protection contre les « bombes de décompression »).
Image.MAX_IMAGE_PIXELS = 40_000_000

NOT_AN_IMAGE = "Ce fichier n'est pas une image lisible (photo JPEG, PNG ou WebP)."


def save_image(upload, folder: str, field: str = "photo", max_side: int = 1600) -> str:
    """Enregistre l'image et renvoie son adresse publique (/media/<dossier>/<nom>.webp)."""
    if upload is None:
        raise ValidationError({field: "Choisissez une image."})
    if upload.size > MAX_BYTES:
        raise ValidationError({field: "Image trop lourde : 8 Mo au plus."})
    try:
        with Image.open(upload) as probe:
            probe.verify()  # fichier tronqué ou déguisé : refusé
        upload.seek(0)
        with Image.open(upload) as original:
            image = ImageOps.exif_transpose(original)  # redressée, comme sur le téléphone
            has_alpha = "A" in image.getbands()
            image = image.convert("RGBA" if has_alpha else "RGB")
            image.thumbnail((max_side, max_side))
            out = BytesIO()
            # Aucune métadonnée transmise : l'EXIF (GPS, appareil, date) n'est pas recopié.
            image.save(out, "WEBP", quality=80, method=4)
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as exc:
        raise ValidationError({field: NOT_AN_IMAGE}) from exc
    path = default_storage.save(f"{folder}/{uuid4().hex}.webp", ContentFile(out.getvalue()))
    return f"{settings.MEDIA_URL}{path}"


def delete_image(url: str) -> None:
    """Supprime une image envoyée (les images fournies avec le site, /images/…, restent)."""
    if url and url.startswith(settings.MEDIA_URL):
        with suppress(OSError):
            default_storage.delete(url.removeprefix(settings.MEDIA_URL))
