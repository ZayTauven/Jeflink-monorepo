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
from django.core.files.storage import FileSystemStorage, default_storage
from PIL import Image, ImageOps
from rest_framework.exceptions import ValidationError

MAX_BYTES = 8 * 1024 * 1024
# Une photo de téléphone fait 12 à 48 Mpx. Au-delà de 24 Mpx, refusée avant décodage : un PNG
# de quelques Ko peut sinon occuper des centaines de Mo (« bombe de décompression »).
MAX_PIXELS = 24_000_000
Image.MAX_IMAGE_PIXELS = MAX_PIXELS  # filet de sécurité de Pillow (il ne lève qu'au double)
FORMATS = ("JPEG", "PNG", "WEBP")  # pas de TIFF, PSD, EPS… : moins de décodeurs exposés
NAME = re.compile(r"[0-9a-f]{32}\.webp")

NOT_AN_IMAGE = "Ce fichier n'est pas une image lisible (photo JPEG, PNG ou WebP)."
NOT_A_DOCUMENT = "Ce fichier n'est ni une photo lisible (JPEG, PNG, WebP) ni un PDF."


def _check_size(upload, field: str, missing: str):
    if upload is None:
        raise ValidationError({field: missing})
    if upload.size > MAX_BYTES:
        raise ValidationError({field: "Fichier trop lourd : 8 Mo au plus."})


def _encode(upload, field: str, max_side: int, unreadable: str = NOT_AN_IMAGE) -> bytes:
    """Photo vérifiée, réduite, redressée, sans métadonnées → octets WebP."""
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
        raise ValidationError({field: unreadable}) from exc
    return out.getvalue()


def save_image(upload, folder: str, field: str = "photo", max_side: int = 1600) -> str:
    """Enregistre l'image et renvoie son adresse publique (/media/<dossier>/<nom>.webp)."""
    _check_size(upload, field, "Choisissez une image.")
    data = _encode(upload, field, max_side)
    path = default_storage.save(f"{folder}/{uuid4().hex}.webp", ContentFile(data))
    return f"{settings.MEDIA_URL}{path}"


# --- Documents privés (pièce d'identité, attestations des pros) --------------------------------


def private_storage() -> FileSystemStorage:
    """Hors de MEDIA_ROOT : jamais servis sous /media/, seulement par une vue qui contrôle."""
    return FileSystemStorage(location=settings.PRIVATE_ROOT, base_url=None)


def save_document(upload, field: str = "file") -> tuple[str, str]:
    """Photo (ré-encodée en WebP, lisible, sans métadonnées) ou PDF (gardé tel quel, toujours
    téléchargé, jamais affiché dans une page). Renvoie (chemin privé, type de contenu)."""
    _check_size(upload, field, "Choisissez un fichier.")
    head = upload.read(5)
    upload.seek(0)
    if head == b"%PDF-":
        name, content, kind = f"{uuid4().hex}.pdf", upload, "application/pdf"
    else:
        data = _encode(upload, field, 2000, NOT_A_DOCUMENT)  # assez grand pour lire une pièce
        name, content, kind = f"{uuid4().hex}.webp", ContentFile(data), "image/webp"
    return private_storage().save(f"documents/{name}", content), kind


def delete_document(path: str) -> None:
    if re.fullmatch(r"documents/[0-9a-f]{32}\.(webp|pdf)", path or ""):
        with suppress(OSError):
            private_storage().delete(path)


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
