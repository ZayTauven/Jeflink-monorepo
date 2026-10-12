"""Produit les images Jeflink du site (WebP) depuis references/assets-originaux.

Usage (depuis la racine du dépôt) : uv run --directory apps/api --with pillow python ../web/scripts/build-images.py
Les fichiers produits (apps/web/public/images/) sont versionnés ; les originaux, lourds, restent
locaux. Chaque ligne de PLAN est la provenance d'une image. Les tailles reprennent celles du
template Crafto pour ne rien changer à la mise en page.
"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageOps

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "references" / "assets-originaux"
OUT = ROOT / "apps" / "web" / "public" / "images"
CRAFTO = ROOT / "references" / "crafto" / "images"


def ji(n: int) -> Path:
    return SRC / f"Jeflink-illustrations ({n}).jpg"


def face(name: str) -> Path:
    return SRC / "Faces" / name


# sortie, source, (largeur, hauteur), point d'intérêt (x, y en 0..1), traitement
PLAN = [
    # Accueil
    ("accueil/etapes.webp", SRC / "assistance.jpg", (865, 700), (0.35, 0.45), "anneaux"),
    # Pros de démo (cartes « équipe »)
    ("pros/mamadou.webp", ji(85), (600, 742), (0.62, 0.45), None),
    ("pros/ousmane.webp", ji(63), (600, 742), (0.5, 0.45), None),
    ("pros/ibrahima.webp", ji(96), (600, 742), (0.42, 0.4), None),
    ("pros/cheikh.webp", ji(94), (600, 742), (0.5, 0.35), None),
    ("pros/fatou.webp", ji(78), (600, 742), (0.5, 0.4), None),
    ("pros/aliou.webp", ji(84), (600, 742), (0.48, 0.4), None),
    # Clients de démo (avatars des avis)
    ("clients/awa.webp", face("Face (4).jpeg"), (256, 256), (0.5, 0.45), None),
    ("clients/moussa.webp", face("351de301-1617-4a36-95e2-1fa6c3dd1d2d.jpg"), (256, 256), (0.5, 0.45), None),
    ("clients/aminata.webp", face("Face (6).jpeg"), (256, 256), (0.5, 0.45), None),
    ("clients/mariama.webp", face("Face (7).jpeg"), (256, 256), (0.5, 0.45), None),
    ("clients/babacar.webp", face("Face (16).jpeg"), (256, 256), (0.5, 0.45), None),
    ("clients/pape.webp", face("3a7bd2cc-9474-43bf-9e72-b325e395f324.jpg"), (256, 256), (0.5, 0.45), None),
    # À propos
    ("a-propos/titre.webp", ji(83), (1163, 700), (0.45, 0.4), None),
    ("a-propos/pros.webp", ji(54), (567, 700), (0.5, 0.4), None),
    ("a-propos/galerie-1.webp", ji(79), (567, 550), (0.5, 0.45), None),
    ("a-propos/galerie-2.webp", ji(81), (646, 550), (0.5, 0.45), None),
    ("a-propos/galerie-3.webp", ji(97), (758, 550), (0.55, 0.5), None),
    ("a-propos/galerie-4.webp", ji(76), (567, 550), (0.5, 0.45), None),
    ("a-propos/galerie-5.webp", ji(56), (646, 550), (0.5, 0.5), None),
    ("a-propos/galerie-6.webp", ji(71), (758, 550), (0.5, 0.5), None),
    # Comment ça marche
    ("services/titre.webp", SRC / "assistance (3).jpg", (1163, 700), (0.45, 0.45), None),
    ("services/etape-1.webp", ji(100), (679, 525), (0.45, 0.45), "anneaux"),
    ("services/etape-2.webp", ji(82), (679, 525), (0.5, 0.5), None),
    ("services/etape-3.webp", ji(80), (679, 525), (0.5, 0.35), None),
    ("services/pros.webp", ji(74), (567, 700), (0.5, 0.4), None),
    # Métiers
    ("metiers/titre.webp", ji(93), (1163, 700), (0.5, 0.5), None),
    ("metiers/plomberie.webp", ji(68), (865, 800), (0.5, 0.5), None),
    ("metiers/electricite.webp", ji(53), (865, 800), (0.45, 0.5), None),
    ("metiers/climatisation.webp", ji(66), (865, 800), (0.6, 0.35), None),
    ("metiers/electromenager.webp", ji(91), (865, 800), (0.5, 0.5), None),
    ("metiers/menage.webp", ji(69), (865, 800), (0.45, 0.55), None),
    ("metiers/petits-travaux.webp", ji(58), (865, 800), (0.5, 0.5), None),
]


def cover(img: Image.Image, size: tuple[int, int], focus: tuple[float, float]) -> Image.Image:
    """Recadre en « cover » autour du point d'intérêt, puis redimensionne."""
    img = ImageOps.exif_transpose(img).convert("RGB")
    tw, th = size
    w, h = img.size
    scale = max(tw / w, th / h)
    cw, ch = tw / scale, th / scale
    cw, ch = min(cw, w), min(ch, h)
    left = max(0.0, min(focus[0] * w - cw / 2, w - cw))
    top = max(0.0, min(focus[1] * h - ch / 2, h - ch))
    return img.resize(size, Image.LANCZOS, box=(left, top, left + cw, top + ch))


def ring(size, center, outer, thickness, colors, opacity):
    """Anneau en dégradé, calculé sur sa propre boîte : couleur 1 en bas à gauche → couleur 2."""
    w, h = size
    cx, cy = center
    box = int(outer * 2)
    # Dégradé diagonal 0 (bas gauche) → 255 (haut droite), sans rotation ni coins parasites.
    vertical = Image.linear_gradient("L").resize((box, box))  # 0 en haut → 255 en bas
    horizontal = vertical.transpose(Image.Transpose.ROTATE_90).transpose(Image.Transpose.FLIP_LEFT_RIGHT)
    grad = Image.blend(horizontal, ImageOps.invert(vertical), 0.5)
    local = Image.composite(Image.new("RGB", (box, box), colors[1]), Image.new("RGB", (box, box), colors[0]), grad)
    color = Image.new("RGB", size, colors[1])
    color.paste(local, (int(cx - outer), int(cy - outer)))
    mask = Image.new("L", size, 0)
    d = ImageDraw.Draw(mask)
    d.ellipse((cx - outer, cy - outer, cx + outer, cy + outer), fill=int(255 * opacity))
    inner = outer - thickness
    d.ellipse((cx - inner, cy - inner, cx + inner, cy + inner), fill=0)
    mask = mask.filter(ImageFilter.GaussianBlur(1.2))
    layer = color.convert("RGBA")
    layer.putalpha(mask)
    return layer


def anneaux(img: Image.Image) -> Image.Image:
    """Le traitement de la photo phare du template : deux anneaux orange, teinte chaude."""
    w, h = img.size
    warm = Image.new("RGB", img.size, (255, 186, 120))
    img = Image.blend(img, warm, 0.06).convert("RGBA")
    img.alpha_composite(
        ring(img.size, (0.05 * w, 0.14 * h), 0.19 * w, 0.075 * w, ("#ffc21a", "#f55608"), 0.95)
    )
    img.alpha_composite(
        ring(img.size, (0.98 * w, 1.08 * h), 0.5 * w, 0.1 * w, ("#f55608", "#ff8a2a"), 0.72)
    )
    return img.convert("RGB")


def avatars() -> None:
    """Groupe de trois visages ronds qui se chevauchent (remplace l'image d'avatars du template)."""
    names = ["Face (5).jpeg", "Face (17).jpeg", "Face (8).jpeg"]
    size, d, border = 172, 140, 6
    out = Image.new("RGBA", (d + 2 * border + 2 * (d - 36), size), (0, 0, 0, 0))
    for i, name in enumerate(names):
        photo = cover(Image.open(face(name)), (d, d), (0.5, 0.45)).convert("RGBA")
        mask = Image.new("L", (d * 4, d * 4), 0)
        ImageDraw.Draw(mask).ellipse((0, 0, d * 4, d * 4), fill=255)
        mask = mask.resize((d, d), Image.LANCZOS)
        disc = Image.new("RGBA", (d + 2 * border, d + 2 * border), (0, 0, 0, 0))
        ring_mask = Image.new("L", ((d + 2 * border) * 4,) * 2, 0)
        ImageDraw.Draw(ring_mask).ellipse((0, 0, (d + 2 * border) * 4, (d + 2 * border) * 4), fill=255)
        disc.paste((255, 255, 255, 255), (0, 0), ring_mask.resize(disc.size, Image.LANCZOS))
        disc.paste(photo, (border, border), mask)
        out.alpha_composite(disc, (i * (d - 36), (size - disc.size[1]) // 2))
    target = OUT / "a-propos" / "avatars.webp"
    target.parent.mkdir(parents=True, exist_ok=True)
    out.save(target, "WEBP", quality=85)


def laurel() -> None:
    """Couronne de laurier des badges du template, vidée de son texte (on écrit le nôtre en HTML)."""
    img = Image.open(CRAFTO / "demo-marketing-strategy-rating-01.png").convert("RGBA")
    w, h = img.size
    px = img.load()
    for x in range(int(w * 0.25), int(w * 0.75)):
        for y in range(h):
            px[x, y] = (0, 0, 0, 0)
    target = OUT / "accueil" / "laurier.png"
    target.parent.mkdir(parents=True, exist_ok=True)
    img.save(target)


def main() -> None:
    for out, src, size, focus, treatment in PLAN:
        img = cover(Image.open(src), size, focus)
        if treatment == "anneaux":
            img = anneaux(img)
        target = OUT / out
        target.parent.mkdir(parents=True, exist_ok=True)
        img.save(target, "WEBP", quality=80, method=6)
        print(f"{out:34} <- {src.name}")
    avatars()
    laurel()


if __name__ == "__main__":
    main()
