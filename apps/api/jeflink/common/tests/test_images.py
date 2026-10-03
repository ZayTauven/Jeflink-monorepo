"""Réencodage d'images (ADR 0011) : sans métadonnée, redressé, borné, type vérifié par décodage."""

import io

import pytest
from PIL import Image

from jeflink.common.images import InvalidImage, reencode

GPS_IFD = 0x8825


def jpeg_with_gps(size=(300, 200), orientation=1) -> bytes:
    image = Image.new("RGB", size, (200, 30, 30))
    exif = Image.Exif()
    exif[0x010F] = "AppareilTest"  # Make
    exif[0x0112] = orientation
    exif[GPS_IFD] = {1: "N", 2: (14.0, 41.0, 30.0), 3: "W", 4: (17.0, 26.0, 0.0)}
    out = io.BytesIO()
    image.save(out, format="JPEG", exif=exif)
    return out.getvalue()


def test_le_gps_et_tout_l_exif_sont_retires():
    source = jpeg_with_gps()
    assert Image.open(io.BytesIO(source)).getexif().get_ifd(GPS_IFD)  # la source en porte bien
    result = reencode(source, max_edge=1600, quality=75)
    out = Image.open(io.BytesIO(result.content))
    assert out.format == "WEBP"
    assert len(out.getexif()) == 0 and not out.getexif().get_ifd(GPS_IFD)
    assert not {"exif", "xmp", "icc_profile"} & set(out.info)
    for marker in (b"EXIF", b"XMP ", b"ICCP", b"AppareilTest", b"Exif"):
        assert marker not in result.content


def test_orientation_appliquee_aux_pixels():
    # 300 x 200 marquée « tourner de 90° » : le résultat est en portrait.
    result = reencode(jpeg_with_gps(size=(300, 200), orientation=6), max_edge=1600, quality=75)
    assert (result.width, result.height) == (200, 300)


def test_reduit_le_cote_long_sans_agrandir():
    big = Image.new("RGB", (3200, 1200), (10, 10, 10))
    out = io.BytesIO()
    big.save(out, format="PNG")
    result = reencode(out.getvalue(), max_edge=1600, quality=75)
    assert (result.width, result.height) == (1600, 600)
    small = reencode(jpeg_with_gps(size=(120, 80)), max_edge=1600, quality=75)
    assert (small.width, small.height) == (120, 80)


def test_png_transparent_sur_fond_blanc():
    out = io.BytesIO()
    Image.new("RGBA", (10, 10), (0, 0, 0, 0)).save(out, format="PNG")
    result = reencode(out.getvalue(), max_edge=1600, quality=100)
    pixel = Image.open(io.BytesIO(result.content)).convert("RGB").getpixel((5, 5))
    assert min(pixel) > 240


@pytest.mark.parametrize(
    "data",
    [
        b"",
        b"pas une image",
        b"<svg xmlns='http://www.w3.org/2000/svg'><script>alert(1)</script></svg>",
        b"%PDF-1.4 ...",
        b"GIF89a\x01\x00\x01\x00\x00\x00\x00;",  # GIF : format non permis
    ],
)
def test_contenu_qui_n_est_pas_une_image_permise_refuse(data):
    with pytest.raises(InvalidImage):
        reencode(data, max_edge=1600, quality=75)


def test_image_tronquee_refusee():
    source = jpeg_with_gps(size=(800, 800))
    with pytest.raises(InvalidImage):
        reencode(source[: len(source) // 2], max_edge=1600, quality=75)


def test_bombe_de_decompression_refusee_avant_decodage(settings):
    settings.IMAGE_MAX_PIXELS = 1_000_000
    out = io.BytesIO()
    Image.new("1", (4000, 4000)).save(out, format="PNG")  # 16 M pixels, quelques Ko
    assert len(out.getvalue()) < 20_000
    with pytest.raises(InvalidImage):
        reencode(out.getvalue(), max_edge=1600, quality=75)


def test_miniature_400_px():
    result = reencode(jpeg_with_gps(size=(1000, 500)), max_edge=400, quality=70)
    assert (result.width, result.height) == (400, 200)
