"""Documents des pros : envoi, accès privé, examen par l'équipe, vérification exigeant une pièce."""

from io import BytesIO

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from jeflink.accounts.models import ProDocument, ProProfile, User
from jeflink.catalog.models import Trade
from jeflink.console.models import AuditLog

pytestmark = pytest.mark.django_db
PASSWORD = "un-mot-de-passe-solide"
PDF = b"%PDF-1.4\n1 0 obj << >> endobj\ntrailer << >>\n%%EOF\n"


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


def photo() -> SimpleUploadedFile:
    out = BytesIO()
    Image.new("RGB", (1200, 800), (200, 200, 200)).save(out, "JPEG")
    return SimpleUploadedFile("cni.jpg", out.getvalue(), content_type="image/jpeg")


@pytest.fixture
def pro():
    user = User.objects.create_user("moussa@example.com", PASSWORD, role=User.Role.PRO)
    ProProfile.objects.create(user=user).trades.add(
        Trade.objects.create(slug="plomberie", name="Plomberie")
    )
    return user


def staff(role: str) -> User:
    return User.objects.create_user(
        f"{role}@jeflink.local", PASSWORD, is_staff=True, staff_role=role
    )


def upload(user, kind="id", file=None):
    return as_user(user).post(
        "/api/auth/me/documents/", {"kind": kind, "file": file or photo()}, format="multipart"
    )


def test_le_pro_envoie_une_photo_ou_un_pdf_prives(pro, _private):
    res = upload(pro)
    assert res.status_code == 201, res.data
    assert res.data["status"] == "pending" and "file" not in res.data
    doc = ProDocument.objects.get(pk=res.data["id"])
    assert doc.content_type == "image/webp" and (_private / doc.file).exists()
    assert not doc.file.startswith("/media/")  # rien de servi publiquement

    pdf = upload(pro, "certificate", SimpleUploadedFile("cap.pdf", PDF))
    assert pdf.status_code == 201 and pdf.data["content_type"] == "application/pdf"

    bad = upload(pro, "certificate", SimpleUploadedFile("x.pdf", b"<html>pas un pdf</html>"))
    assert bad.status_code == 400
    assert upload(pro, "passeport").status_code == 400  # type inconnu
    assert as_user(pro).get("/api/auth/me/").data["pro_profile"]["documents"][0]["kind"] == (
        "certificate"
    )


def test_un_client_n_envoie_pas_de_document():
    client = User.objects.create_user("awa@example.com", PASSWORD)
    assert upload(client).status_code == 403


def test_fichier_lisible_par_son_pro_et_les_operations_seulement(pro):
    doc_id = upload(pro).data["id"]
    pdf_id = upload(pro, "certificate", SimpleUploadedFile("cap.pdf", PDF)).data["id"]
    url = f"/api/auth/documents/{doc_id}/file/"

    mine = as_user(pro).get(url)
    assert mine.status_code == 200 and mine["Content-Type"] == "image/webp"
    assert mine["Cache-Control"] == "private, no-store"
    assert "attachment" not in mine.get("Content-Disposition", "")
    pdf = as_user(staff("ops")).get(f"/api/auth/documents/{pdf_id}/file/")
    assert pdf.status_code == 200 and pdf["Content-Disposition"].startswith("attachment")

    other = User.objects.create_user("autre@example.com", PASSWORD, role=User.Role.PRO)
    ProProfile.objects.create(user=other)
    assert as_user(other).get(url).status_code == 404
    assert as_user(staff("marketing")).get(url).status_code == 404
    assert APIClient().get(url).status_code == 401


def test_examen_par_l_equipe_et_verification(pro):
    ops = staff("ops")
    api = as_user(ops)
    doc_id = upload(pro).data["id"]

    # Sans pièce acceptée, pas de vérification.
    res = api.post(f"/api/console/pros/{pro.pk}/verify/")
    assert res.status_code == 400

    assert api.post(f"/api/console/documents/{doc_id}/reject/", {"reason": ""}).status_code == 400
    res = api.post(f"/api/console/documents/{doc_id}/reject/", {"reason": "Photo floue"})
    assert res.status_code == 200 and res.data["status"] == "rejected"
    assert as_user(pro).get("/api/auth/me/").data["pro_profile"]["documents"][0]["note"] == (
        "Photo floue"
    )
    assert api.post(f"/api/console/documents/{doc_id}/accept/").status_code == 400  # déjà vu

    # Le pro retire le document refusé et en envoie un net.
    assert as_user(pro).delete(f"/api/auth/me/documents/{doc_id}/").status_code == 204
    new_id = upload(pro).data["id"]
    assert api.post(f"/api/console/documents/{new_id}/accept/").status_code == 200
    detail = api.get(f"/api/console/pros/{pro.pk}/").data
    assert detail["has_accepted_id"] and detail["documents"][0]["status"] == "accepted"
    assert api.post(f"/api/console/pros/{pro.pk}/verify/").status_code == 200

    # Accepté, il fonde la vérification : le pro ne peut plus le retirer.
    assert as_user(pro).delete(f"/api/auth/me/documents/{new_id}/").status_code == 400
    assert list(AuditLog.objects.order_by("id").values_list("action", flat=True)) == [
        "document.reject",
        "document.accept",
        "pro.verify",
    ]


def test_examen_reserve_aux_operations(pro):
    doc_id = upload(pro).data["id"]
    res = as_user(staff("marketing")).post(f"/api/console/documents/{doc_id}/accept/")
    assert res.status_code == 403
