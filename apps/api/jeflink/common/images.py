"""Réencodage des images envoyées (ADR 0011) : le seul chemin vers le stockage.

L'image est décodée (le type est vérifié par le contenu, jamais par l'extension), sa taille
décodée est bornée, elle est redressée selon son EXIF, réduite, puis réencodée en WebP **à
partir de ses seuls pixels** : aucune métadonnée (EXIF, GPS, XMP, profil ICC) ne survit. Ni
l'original ni sa position ne sont stockés.
"""

import io
from dataclasses import dataclass

from django.conf import settings
from PIL import Image, ImageOps, UnidentifiedImageError

ALLOWED_FORMATS = ("JPEG", "PNG", "WEBP")


class InvalidImage(ValueError):
    """Image refusée : illisible, mauvais type, trop grande une fois décodée."""


@dataclass(frozen=True)
class EncodedImage:
    content: bytes
    width: int
    height: int

    @property
    def size_bytes(self) -> int:
        return len(self.content)


def _flatten(image: Image.Image) -> Image.Image:
    """Mode RGB ; la transparence est posée sur fond blanc (jamais un fond noir)."""
    if image.mode == "RGB":
        return image
    if image.mode in {"RGBA", "LA", "P", "PA"}:
        rgba = image.convert("RGBA")
        background = Image.new("RGB", rgba.size, (255, 255, 255))
        background.paste(rgba, mask=rgba.getchannel("A"))
        return background
    return image.convert("RGB")


def reencode(data: bytes, *, max_edge: int, quality: int) -> EncodedImage:
    """WebP sans métadonnée, côté long de ``max_edge`` pixels au plus. ``InvalidImage`` sinon."""
    limit = settings.IMAGE_MAX_PIXELS
    Image.MAX_IMAGE_PIXELS = limit
    try:
        with Image.open(io.BytesIO(data), formats=ALLOWED_FORMATS) as source:
            if source.width * source.height > limit:
                raise InvalidImage("too_many_pixels")
            source.load()  # décode vraiment : une image tronquée ou piégée échoue ici
            oriented = ImageOps.exif_transpose(source)
            flat = _flatten(oriented)
    except InvalidImage:
        raise
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError, Image.DecompressionBombError):
        raise InvalidImage("unreadable") from None
    flat.thumbnail((max_edge, max_edge), Image.Resampling.LANCZOS)
    # Pixels seulement : ``info`` (exif, xmp, icc_profile) ne suit jamais.
    clean = Image.frombytes("RGB", flat.size, flat.tobytes())
    out = io.BytesIO()
    clean.save(out, format="WEBP", quality=quality, method=4)
    return EncodedImage(out.getvalue(), clean.width, clean.height)
