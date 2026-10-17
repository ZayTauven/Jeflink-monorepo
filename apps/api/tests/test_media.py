"""Images envoyées : traitement (jeflink/media.py), photo de profil, image des métiers, équipe."""

from io import BytesIO

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image
from rest_framework.authtoken.models import Token
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIClient

from jeflink.accounts.models import ProProfile, User
from jeflink.catalog.models import Trade
from jeflink.console.models import AuditLog
from jeflink.media import save_image

pytestmark = pytest.mark.django_db
PASSWORD = "un-mot-de-passe-solide"


@pytest.fixture(autouse=True)
def _media(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    return tmp_path


def as_user(user):
    client = APIClient()
    token, _ = Token.objects.get_or_create(user=user)
    client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
    return client


def photo(name="photo.jpg", size=(2400, 1200), gps=False) -> SimpleUploadedFile:
    """Photo JPEG de téléphone ; `gps` : avec une position dans les métadonnées EXIF."""
    exif = Image.Exif()
    if gps:
        exif[0x8825] = {1: "N", 2: (14.0, 41.0, 30.0), 3: "W", 4: (17.0, 26.0, 10.0)}
    out = BytesIO()
    Image.new("RGB", size, (245, 86, 8)).save(out, "JPEG", exif=exif)
    return SimpleUploadedFile(name, out.getvalue(), content_type="image/jpeg")


def stored(url: str, root):
    return root / url.removeprefix("/media/")


# --- Traitement --------------------------------------------------------------------------------


def test_image_reduite_en_webp_sans_metadonnees(_media):
    url = save_image(photo(gps=True), "profils")
    assert url.startswith("/media/profils/") and url.endswith(".webp")
    with Image.open(stored(url, _media)) as img:
        assert img.format == "WEBP"
        assert max(img.size) == 1600
        assert not img.getexif()  # plus de position GPS ni d'appareil


@pytest.mark.parametrize(
    "upload",
    [
        SimpleUploadedFile("faux.jpg", b"<script>alert(1)</script>", content_type="image/jpeg"),
        None,
    ],
)
def test_fichier_refuse(upload, _media):
    with pytest.raises(ValidationError):
        save_image(upload, "profils")
    assert not any(_media.rglob("*.webp"))


def test_image_trop_lourde_refusee(_media):
    big = SimpleUploadedFile("lourde.jpg", b"0" * (8 * 1024 * 1024 + 1), content_type="image/jpeg")
    with pytest.raises(ValidationError, match="trop lourde"):
        save_image(big, "profils")


# --- Ma photo ----------------------------------------------------------------------------------


def test_ma_photo_remplacee_puis_retiree(_media):
    awa = User.objects.create_user("awa@example.com", PASSWORD, photo="/images/clients/awa.webp")
    api = as_user(awa)

    first = api.post("/api/auth/me/photo/", {"photo": photo()}, format="multipart")
    assert first.status_code == 200
    url = first.data["photo"]
    assert url.startswith("/media/profils/") and stored(url, _media).exists()
    assert api.get("/api/auth/me/").data["photo"] == url

    second = api.post("/api/auth/me/photo/", {"photo": photo()}, format="multipart").data["photo"]
    assert not stored(url, _media).exists()  # l'ancienne est effacée

    assert api.delete("/api/auth/me/photo/").data["photo"] == ""
    assert not stored(second, _media).exists()


def test_photo_du_pro_sur_son_profil_public(_media):
    pro = User.objects.create_user("moussa@example.com", PASSWORD, role=User.Role.PRO)
    ProProfile.objects.create(user=pro, photo="/images/pros/mamadou.webp")
    url = (
        as_user(pro)
        .post("/api/auth/me/photo/", {"photo": photo()}, format="multipart")
        .data["photo"]
    )
    pro.pro_profile.refresh_from_db()
    assert pro.pro_profile.photo == url


def test_ma_photo_controlee():
    assert APIClient().post("/api/auth/me/photo/", {}, format="multipart").status_code == 401
    awa = User.objects.create_user("awa@example.com", PASSWORD)
    res = as_user(awa).post("/api/auth/me/photo/", {}, format="multipart")
    assert res.status_code == 400 and "photo" in res.data


# --- Console : métiers et équipe ---------------------------------------------------------------


def staff(role: str) -> User:
    return User.objects.create_user(
        f"{role}@jeflink.local", PASSWORD, is_staff=True, staff_role=role
    )


def test_image_du_metier_envoyee_depuis_la_console(_media, django_capture_on_commit_callbacks):
    api = as_user(staff("marketing"))
    res = api.post(
        "/api/console/trades/",
        {"name": "Peinture", "image_file": photo()},
        format="multipart",
    )
    assert res.status_code == 201, res.data
    first = res.data["image"]
    assert first.startswith("/media/metiers/") and stored(first, _media).exists()

    trade = Trade.objects.get(name="Peinture")
    with django_capture_on_commit_callbacks(execute=True):  # l'ancienne est effacée au commit
        res = api.post(
            f"/api/console/trades/{trade.pk}/update/",
            {"name": "Peinture", "image": first, "image_file": photo()},
            format="multipart",
        )
    assert res.status_code == 200
    assert res.data["image"] != first and not stored(first, _media).exists()

    # Formulaire sans nouvel envoi : l'image gardée est acceptée telle quelle.
    res = api.post(
        f"/api/console/trades/{trade.pk}/update/",
        {"name": "Peinture et enduits", "image": res.data["image"]},
        format="json",
    )
    assert res.status_code == 200


def test_image_du_metier_refusee_sans_rien_garder(_media):
    res = as_user(staff("marketing")).post(
        "/api/console/trades/",
        {"name": "Peinture", "image_file": SimpleUploadedFile("x.png", b"pas une image")},
        format="multipart",
    )
    assert res.status_code == 400 and "image_file" in res.data
    assert not Trade.objects.exists() and not any(_media.rglob("*.webp"))


def test_photo_d_un_membre_de_l_equipe(_media, django_capture_on_commit_callbacks):
    boss, ops = staff("super"), staff("ops")
    url = f"/api/console/team/{ops.pk}/photo/"

    assert as_user(ops).post(url, {"photo": photo()}, format="multipart").status_code == 403
    res = as_user(boss).post(url, {"photo": photo()}, format="multipart")
    assert res.status_code == 200 and res.data["photo"].startswith("/media/equipe/")
    assert AuditLog.objects.filter(action=AuditLog.Action.TEAM_PHOTO, target_id=ops.pk).exists()

    with django_capture_on_commit_callbacks(execute=True):
        res = as_user(boss).post(url, {"remove": "1"}, format="multipart")
    assert res.data["photo"] == "" and not any(_media.rglob("*.webp"))
    assert as_user(boss).post(url, {}, format="multipart").status_code == 400


# --- Revue sécurité ----------------------------------------------------------------------------


def test_trop_de_pixels_ou_format_hors_liste_refuse(_media):
    out = BytesIO()
    Image.new("L", (6000, 5000)).save(out, "PNG")  # 30 Mpx, quelques Ko
    with pytest.raises(ValidationError, match="millions de pixels"):
        save_image(SimpleUploadedFile("bombe.png", out.getvalue()), "profils")
    tiff = BytesIO()
    Image.new("RGB", (100, 100)).save(tiff, "TIFF")
    with pytest.raises(ValidationError):
        save_image(SimpleUploadedFile("scan.tif", tiff.getvalue()), "profils")


def test_un_metier_ne_peut_pas_reprendre_la_photo_d_un_compte(_media):
    pro = User.objects.create_user("moussa@example.com", PASSWORD, role=User.Role.PRO)
    ProProfile.objects.create(user=pro)
    url = (
        as_user(pro)
        .post("/api/auth/me/photo/", {"photo": photo()}, format="multipart")
        .data["photo"]
    )
    api = as_user(staff("marketing"))
    res = api.post("/api/console/trades/", {"name": "Peinture", "image": url}, format="json")
    assert res.status_code == 400 and "image" in res.data
    assert stored(url, _media).exists()


def test_la_photo_envoyee_par_un_client_n_est_pas_publiee_avec_ses_avis():
    from jeflink.catalog.views import PublicReviewSerializer

    class Client:
        photo = "/media/profils/" + "a" * 32 + ".webp"

    review = type("R", (), {"request": type("Q", (), {"client": Client})})()
    assert PublicReviewSerializer().get_author_photo(review) == ""
    Client.photo = "/images/clients/awa.webp"  # visage de démo
    assert PublicReviewSerializer().get_author_photo(review) == "/images/clients/awa.webp"
