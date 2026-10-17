"""Photos d'une demande : envoyées par le client, privées, vues par qui voit la demande."""

from io import BytesIO

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from jeflink.accounts.models import ProProfile, User
from jeflink.catalog.models import Trade, Zone
from jeflink.jobs import services
from jeflink.jobs.models import RequestMedia

pytestmark = pytest.mark.django_db
PASSWORD = "un-mot-de-passe-solide"


@pytest.fixture(autouse=True)
def _private(settings, tmp_path):
    settings.PRIVATE_ROOT = tmp_path / "private"
    settings.MEDIA_ROOT = tmp_path / "media"
    return settings.PRIVATE_ROOT


def as_user(user):
    client = APIClient()
    token, _ = Token.objects.get_or_create(user=user)
    client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
    return client


def photo(gps=False) -> SimpleUploadedFile:
    exif = Image.Exif()
    if gps:
        exif[0x8825] = {1: "N", 2: (14.0, 41.0, 30.0)}
    out = BytesIO()
    Image.new("RGB", (3000, 2000), (120, 90, 60)).save(out, "JPEG", exif=exif)
    return SimpleUploadedFile("fuite.jpg", out.getvalue(), content_type="image/jpeg")


@pytest.fixture
def world():
    trade = Trade.objects.create(slug="plomberie", name="Plomberie")
    other_trade = Trade.objects.create(slug="menage", name="Ménage")
    zone = Zone.objects.create(slug="ouakam", name="Ouakam")
    client = User.objects.create_user("awa@example.com", PASSWORD)
    pro = User.objects.create_user("moussa@example.com", PASSWORD, role=User.Role.PRO)
    ProProfile.objects.create(user=pro, is_verified=True).trades.add(trade)
    stranger = User.objects.create_user("binta@example.com", PASSWORD, role=User.Role.PRO)
    ProProfile.objects.create(user=stranger, is_verified=True).trades.add(other_trade)
    req = services.create_request(
        client, trade=trade, zone=zone, title="Fuite", description="Sous l'évier"
    )
    return {"client": client, "pro": pro, "stranger": stranger, "req": req}


def add(user, req, file=None):
    return as_user(user).post(
        f"/api/requests/{req.pk}/photos/", {"photo": file or photo()}, format="multipart"
    )


def test_le_client_joint_trois_photos_au_plus(world, _private):
    client, req = world["client"], world["req"]
    res = add(client, req, photo(gps=True))
    assert res.status_code == 201, res.data
    assert len(res.data["photos"]) == 1
    media = RequestMedia.objects.get()
    assert (_private / media.file).exists() and media.file.startswith("demandes/")
    with Image.open(_private / media.file) as img:
        assert img.format == "WEBP" and max(img.size) == 1600 and not img.getexif()

    add(client, req)
    add(client, req)
    assert add(client, req).status_code == 400  # 3 au plus
    assert add(world["pro"], req).status_code in (403, 404)  # seul le client


def test_qui_voit_la_photo(world):
    client, req = world["client"], world["req"]
    media_id = add(client, req).data["photos"][0]["id"]
    url = f"/api/requests/{req.pk}/photos/{media_id}/file/"

    for user in (client, world["pro"]):
        res = as_user(user).get(url)
        assert res.status_code == 200 and res["Content-Type"] == "image/webp"
        assert res["Cache-Control"] == "private, no-store"
    ops = User.objects.create_user("ops@jeflink.local", PASSWORD, is_staff=True, staff_role="ops")
    assert as_user(ops).get(url).status_code == 200
    marketing = User.objects.create_user(
        "mk@jeflink.local", PASSWORD, is_staff=True, staff_role="marketing"
    )
    assert as_user(marketing).get(url).status_code == 404
    assert as_user(world["stranger"]).get(url).status_code == 404  # autre métier
    assert APIClient().get(url).status_code == 401
    # Une photo d'une autre demande, même visible : introuvable sous celle-ci.
    other = services.create_request(
        client, trade=req.trade, zone=req.zone, title="Autre", description="…"
    )
    assert as_user(client).get(f"/api/requests/{other.pk}/photos/{media_id}/file/").status_code == (
        404
    )


def test_retirer_une_photo_puis_plus_rien_apres_annulation(world, _private):
    client, req = world["client"], world["req"]
    data = add(client, req).data
    media = RequestMedia.objects.get()
    res = as_user(client).delete(f"/api/requests/{req.pk}/photos/{data['photos'][0]['id']}/")
    assert res.status_code == 200 and res.data["photos"] == []
    assert not (_private / media.file).exists()

    add(client, req)
    services.cancel(client, req, reason="other", note="Réparé moi-même")
    assert add(client, req).status_code == 400  # demande annulée : photos figées
