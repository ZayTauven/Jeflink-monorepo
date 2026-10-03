"""Photos d'intervention (spec 004, tâche 5) : envoi idempotent et réencodé, limites, miniature,
signalement, purge, anonymiseur, rétention du repère. Stockage en mémoire : aucun réseau."""

import io
import re
from datetime import timedelta

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from jeflink.accounts.tests.factories import CompleteUserFactory
from jeflink.bookings import services, tasks
from jeflink.bookings.machine import Status
from jeflink.bookings.models import Booking, BookingPhoto
from jeflink.common import storage
from jeflink.common.tests.test_images import GPS_IFD, jpeg_with_gps
from jeflink.providers.models import Provider
from jeflink.providers.tests.factories import VerifiedProviderFactory
from jeflink.requests.tests.test_requests_api import bearer
from jeflink.trust.models import AuditEvent

from .factories import advance, scheduled
from .test_services import expect

pytestmark = pytest.mark.django_db
KEY = "photo-key-" + "0" * 22


def key(n: int = 0) -> str:
    return f"photo-key-{n:022d}"


def upload(booking, *, phase="before", content=None, n=0, **kwargs):
    return services.upload_photo(
        booking=booking,
        actor=booking.provider.owner,
        phase=phase,
        content=content if content is not None else jpeg_with_gps(size=(900, 600)),
        idempotency_key=key(n),
        **kwargs,
    )


def on_site():
    scene, booking = scheduled()
    return scene, advance(booking, Status.ON_SITE)


def stored_objects(path: str = "") -> list[str]:
    dirs, files = storage.photos_storage().listdir(path)
    found = [f"{path}{name}" for name in files]
    for directory in dirs:
        found += stored_objects(f"{path}{directory}/")
    return found


# --- Envoi -------------------------------------------------------------------------------------


def test_envoi_reencode_sans_exif_ni_gps_et_cles_sans_donnee_personnelle():
    _, booking = on_site()
    result = upload(booking)
    photo = result.photo
    assert result.created and photo.status == "processing" and photo.phase == "before"
    assert photo.image_key == f"bookings/{booking.public_id}/{photo.public_id}.webp"
    assert photo.thumb_key == ""
    stored = storage.read(photo.image_key)
    image = Image.open(io.BytesIO(stored))
    assert image.format == "WEBP" and not image.getexif().get_ifd(GPS_IFD)
    assert len(image.getexif()) == 0 and b"EXIF" not in stored
    assert (photo.width, photo.height, photo.size_bytes) == (900, 600, len(stored))
    # Seul le WebP réencodé est stocké : ni l'original, ni autre chose.
    assert stored_objects() == [photo.image_key]
    audit = AuditEvent.objects.get(action="bookings.photo.uploaded")
    assert audit.metadata == {"phase": "before"} and audit.target_public_id == photo.public_id
    assert re.fullmatch(r"bookings/[0-9a-f-]{36}/[0-9a-f-]{36}\.webp", photo.image_key)


def test_la_photo_compte_pour_le_gate_de_start():
    _, booking = on_site()
    with expect("before_photos_required", 422):
        services.start_work(booking=booking, actor=booking.provider.owner)
    upload(booking)
    assert services.start_work(booking=booking, actor=booking.provider.owner).status == (
        Status.IN_PROGRESS
    )


def test_une_photo_signalee_ne_compte_plus_pour_le_gate():
    scene, booking = on_site()
    photo = upload(booking).photo
    services.report_photo(booking=booking, photo_public_id=photo.public_id, actor=scene.client)
    with expect("before_photos_required", 422):
        services.start_work(booking=booking, actor=booking.provider.owner)


def test_envoi_rejoue_ne_cree_pas_de_deuxieme_photo():
    _, booking = on_site()
    content = jpeg_with_gps()
    first = upload(booking, content=content)
    again = upload(booking, content=content)
    assert (first.created, again.created) == (True, False)
    assert again.photo.pk == first.photo.pk and BookingPhoto.objects.count() == 1
    assert len(stored_objects()) == 1
    assert AuditEvent.objects.filter(action="bookings.photo.uploaded").count() == 1


def test_meme_cle_autre_fichier_ou_autre_phase_refuse():
    _, booking = on_site()
    upload(booking, content=jpeg_with_gps(size=(300, 200)))
    with expect("idempotency_key_reused"):
        upload(booking, content=jpeg_with_gps(size=(310, 200)))
    with expect("idempotency_key_reused"):
        upload(booking, phase="after", content=jpeg_with_gps(size=(300, 200)))


@pytest.mark.parametrize("bad_key", ["", "court", "a b c" * 8])
def test_cle_d_idempotence_obligatoire(bad_key):
    _, booking = on_site()
    with expect("idempotency_key_required", 400):
        services.upload_photo(
            booking=booking, actor=booking.provider.owner, phase="before",
            content=jpeg_with_gps(), idempotency_key=bad_key,
        )  # fmt: skip


def test_cinq_photos_par_phase_au_plus():
    _, booking = on_site()
    for n in range(5):
        upload(booking, n=n, content=jpeg_with_gps(size=(300 + n, 200)))
    with expect("photo_limit_reached"):
        upload(booking, n=5, content=jpeg_with_gps(size=(400, 200)))
    assert upload(booking, phase="after", n=6).created  # l'autre phase a ses propres places
    assert BookingPhoto.objects.filter(phase="before").count() == 5


def test_la_limite_est_un_reglage(settings):
    settings.BOOKING_PHOTO_MAX_PER_PHASE = 1
    _, booking = on_site()
    upload(booking)
    with expect("photo_limit_reached"):
        upload(booking, n=1, content=jpeg_with_gps(size=(301, 200)))


def test_trop_gros_image_invalide_et_bombe_de_decompression(settings):
    _, booking = on_site()
    settings.BOOKING_PHOTO_MAX_BYTES = 1000
    with expect("photo_too_large", 413):
        upload(booking, content=jpeg_with_gps(size=(900, 600)))
    settings.BOOKING_PHOTO_MAX_BYTES = 8 * 1024 * 1024
    for bad in (b"pas une image", b"<svg/>", b"%PDF-1.4"):
        with expect("photo_invalid", 422):
            upload(booking, content=bad)
    settings.IMAGE_MAX_PIXELS = 1_000_000
    bomb = io.BytesIO()
    Image.new("1", (4000, 4000)).save(bomb, format="PNG")
    with expect("photo_invalid", 422):
        upload(booking, content=bomb.getvalue())
    assert not BookingPhoto.objects.exists() and stored_objects() == []


def test_phase_inconnue_et_prise_de_vue_dans_le_futur():
    _, booking = on_site()
    with expect("photo_invalid", 422):
        upload(booking, phase="pendant")
    with expect("photo_invalid", 422):
        upload(booking, taken_at=timezone.now() + timedelta(hours=2))
    declared = timezone.now() - timedelta(minutes=3)
    assert upload(booking, taken_at=declared).photo.taken_at == declared


@pytest.mark.parametrize(
    ("status", "allowed"),
    [
        (Status.SCHEDULED, False),
        (Status.EN_ROUTE, False),
        (Status.ON_SITE, True),
        (Status.IN_PROGRESS, True),
        (Status.COMPLETED, True),
        (Status.DISPUTED, True),
        (Status.CLOSED, False),
        (Status.CANCELLED, False),
    ],
)
def test_envoi_ouvert_de_on_site_a_disputed(status, allowed):
    _, booking = scheduled()
    Booking.objects.filter(pk=booking.pk).update(
        status=status, cancelled_by="system" if status == Status.CANCELLED else ""
    )
    if allowed:
        assert upload(booking).created
    else:
        with expect("transition_not_allowed"):
            upload(booking)


def test_un_pro_suspendu_n_envoie_que_pour_une_intervention_en_cours():
    _, booking = scheduled()
    booking = advance(booking, Status.ON_SITE)
    Provider.objects.filter(pk=booking.provider_id).update(status="suspended")
    with expect("provider_not_verified", 403):
        upload(booking)
    Booking.objects.filter(pk=booking.pk).update(status=Status.IN_PROGRESS)
    assert upload(booking).created


def test_autre_pro_refuse():
    _, booking = on_site()
    with expect("not_found", 404):
        services.upload_photo(
            booking=booking, actor=VerifiedProviderFactory().owner, phase="before",
            content=jpeg_with_gps(), idempotency_key=key(),
        )  # fmt: skip


def test_rien_ne_reste_dans_le_stockage_si_la_base_refuse(monkeypatch):
    _, booking = on_site()

    def boom(*args, **kwargs):
        raise RuntimeError("base indisponible")

    monkeypatch.setattr("jeflink.bookings.services.audit", boom)
    with pytest.raises(RuntimeError):
        upload(booking)
    assert stored_objects() == [] and not BookingPhoto.objects.exists()


# --- Miniature ---------------------------------------------------------------------------------


def test_la_miniature_est_produite_apres_le_commit(django_capture_on_commit_callbacks):
    _, booking = on_site()
    with django_capture_on_commit_callbacks(execute=True):
        photo = upload(booking, content=jpeg_with_gps(size=(1000, 500))).photo
    photo.refresh_from_db()
    assert photo.status == "ready"
    assert photo.thumb_key == f"bookings/{booking.public_id}/{photo.public_id}-thumb.webp"
    thumb = Image.open(io.BytesIO(storage.read(photo.thumb_key)))
    assert (thumb.width, thumb.height) == (400, 200) and not thumb.getexif()


def test_la_miniature_est_idempotente_et_gere_les_cas_limites(monkeypatch):
    _, booking = on_site()
    photo = upload(booking).photo
    assert tasks.make_thumbnail(str(photo.public_id)) is True
    writes = []
    real_put = storage.put
    monkeypatch.setattr(storage, "put", lambda *a, **k: writes.append(a[0]) or real_put(*a, **k))
    assert tasks.make_thumbnail(str(photo.public_id)) is False  # déjà prête : rien n'est réécrit
    assert writes == []
    assert tasks.make_thumbnail("00000000-0000-0000-0000-000000000000") is False
    gone = upload(booking, n=1, content=jpeg_with_gps(size=(500, 300))).photo
    storage.delete(gone.image_key)
    assert tasks.make_thumbnail(str(gone.public_id)) is False
    gone.refresh_from_db()
    assert gone.status == "failed"
    assert not BookingPhoto.objects.visible().filter(pk=gone.pk).exists()


# --- Signalement -------------------------------------------------------------------------------


def test_le_client_signale_une_photo_elle_disparait_pour_les_deux():
    scene, booking = on_site()
    photo = upload(booking).photo
    kept = upload(booking, n=1, content=jpeg_with_gps(size=(500, 300))).photo
    services.report_photo(booking=booking, photo_public_id=photo.public_id, actor=scene.client)
    photo.refresh_from_db()
    assert photo.hidden_at and photo.hidden_by == scene.client
    assert [p.pk for p in BookingPhoto.objects.visible()] == [kept.pk]
    # L'Ops la garde : la ligne et l'objet existent encore.
    assert storage.exists(photo.image_key)
    audit = AuditEvent.objects.get(action="bookings.photo.reported")
    assert audit.metadata == {"phase": "before"}
    services.report_photo(booking=booking, photo_public_id=photo.public_id, actor=scene.client)
    assert AuditEvent.objects.filter(action="bookings.photo.reported").count() == 1  # rejeu


def test_signalement_refuse_a_un_autre_compte_ou_pour_une_photo_inconnue():
    scene, booking = on_site()
    photo = upload(booking).photo
    with expect("not_found", 404):
        services.report_photo(
            booking=booking, photo_public_id=photo.public_id, actor=CompleteUserFactory()
        )
    with expect("not_found", 404):
        services.report_photo(
            booking=booking,
            photo_public_id="00000000-0000-0000-0000-000000000000",
            actor=scene.client,
        )


# --- Rétention : photos 12 mois, repère 90 jours ------------------------------------------------


def closed_booking(*, months_ago: float):
    scene, booking = on_site()
    photo = upload(booking).photo
    BookingPhoto.objects.filter(pk=photo.pk).update(thumb_key="t", status="ready")
    storage.put("t", b"x")
    Booking.objects.filter(pk=booking.pk).update(
        status=Status.CLOSED, closed_at=timezone.now() - timedelta(days=30 * months_ago)
    )
    return scene, booking, photo


def test_purge_a_12_mois_supprime_les_objets_et_garde_la_ligne(
    django_capture_on_commit_callbacks,
):
    _, _, old = closed_booking(months_ago=13)
    _, _, recent = closed_booking(months_ago=11)
    with django_capture_on_commit_callbacks(execute=True):
        assert services.purge_photos() == 1
    old.refresh_from_db()
    recent.refresh_from_db()
    assert old.purged_at and old.image_key == "" and old.thumb_key == ""
    assert recent.purged_at is None and storage.exists(recent.image_key)
    assert not storage.exists("t")  # la miniature de la photo purgée est supprimée aussi
    with django_capture_on_commit_callbacks(execute=True):
        assert tasks.purge_photos() == 0  # idempotente
    audit = AuditEvent.objects.get(action="bookings.photos.purged")
    assert audit.actor_kind == "system" and audit.metadata == {"count": 1, "reason": "retention"}


def test_la_retention_est_un_reglage(settings, django_capture_on_commit_callbacks):
    settings.BOOKING_PHOTO_RETENTION = timedelta(days=10)
    closed_booking(months_ago=1)
    with django_capture_on_commit_callbacks(execute=True):
        assert services.purge_photos() == 1


def test_le_repere_et_la_position_sont_vides_90_jours_apres_la_cloture():
    from django.contrib.gis.geos import Point

    scene, booking, _ = closed_booking(months_ago=2)  # 60 jours
    type(scene.request).objects.filter(pk=scene.request.pk).update(
        location=Point(-17.4, 14.7, srid=4326)
    )
    assert services.purge_contact() == 0
    scene.request.refresh_from_db()
    assert scene.request.landmark and scene.request.location
    Booking.objects.filter(pk=booking.pk).update(closed_at=timezone.now() - timedelta(days=91))
    assert services.purge_contact() == 1
    scene.request.refresh_from_db()
    assert scene.request.landmark == "" and scene.request.location is None
    assert tasks.purge_contact() == 0  # idempotente


def test_le_repere_d_une_reservation_non_close_reste():
    scene, _ = on_site()
    assert services.purge_contact() == 0
    scene.request.refresh_from_db()
    assert scene.request.landmark


def test_l_anonymiseur_supprime_les_objets_apres_le_commit(django_capture_on_commit_callbacks):
    scene, booking, photo = closed_booking(months_ago=1)
    other_scene, other_booking, other = closed_booking(months_ago=1)
    with django_capture_on_commit_callbacks(execute=False) as callbacks:
        services.anonymize_bookings(scene.client)
    assert storage.exists(photo.image_key)  # rien avant le commit
    for callback in callbacks:
        callback()
    photo.refresh_from_db()
    assert photo.purged_at and not storage.exists(
        f"bookings/{booking.public_id}/{photo.public_id}.webp"
    )
    other.refresh_from_db()
    assert other.purged_at is None and storage.exists(other.image_key)
    assert other_scene and other_booking


def test_l_anonymiseur_couvre_aussi_le_gerant(django_capture_on_commit_callbacks):
    _, booking, photo = closed_booking(months_ago=1)
    with django_capture_on_commit_callbacks(execute=True):
        services.anonymize_bookings(booking.provider.owner)
    photo.refresh_from_db()
    assert photo.purged_at is not None


def test_drapeaux_photos_manquantes_par_pro():
    scene, booking = on_site()
    booking = advance(booking, Status.IN_PROGRESS)  # photos_pending : aucune photo envoyée
    Booking.objects.filter(pk=booking.pk).update(
        status=Status.CLOSED, completed_at=timezone.now(), closed_at=timezone.now()
    )
    flags = services.missing_photos(booking.provider)
    assert flags == {"closed": 1, "before_photos_missing": 1, "after_photos_missing": 1}
    Booking.objects.filter(pk=booking.pk).update(status=Status.IN_PROGRESS)
    upload(booking)  # l'envoi n'est plus ouvert une fois close : on le fait avant la clôture
    Booking.objects.filter(pk=booking.pk).update(status=Status.CLOSED)
    assert services.missing_photos(booking.provider)["before_photos_missing"] == 0
    assert scene.client


def test_client_refuses_avec_une_photo_apres_est_accepte():
    _, booking = on_site()
    booking = advance(booking, Status.IN_PROGRESS)
    upload(booking, phase="after", n=3)
    done = services.complete_work(
        booking=booking, actor=booking.provider.owner, no_code_reason="client_refuses"
    )
    assert done.status == Status.COMPLETED and done.completion_method == "no_code"


def test_l_admin_des_pros_montre_les_photos_manquantes(client, monkeypatch):
    from django.contrib.auth.models import Group

    from jeflink.accounts.models import User

    monkeypatch.setattr("jeflink.accounts.admin_site.admin_mfa_valid", lambda request: True)
    _, booking = on_site()
    booking = advance(booking, Status.IN_PROGRESS)
    Booking.objects.filter(pk=booking.pk).update(
        status=Status.CLOSED, completed_at=timezone.now(), closed_at=timezone.now()
    )
    ops = User.objects.create_user("+221770000889", is_staff=True)
    ops.groups.add(Group.objects.get(name="Validation pros"))
    client.force_login(ops)
    page = client.get(reverse("admin:providers_provider_changelist"))
    assert page.status_code == 200 and "1 / 1 sur 1" in page.content.decode()


# --- API ---------------------------------------------------------------------------------------


def post_photo(api, booking, *, phase="before", content=None, key_value=KEY, **extra):
    file = SimpleUploadedFile(
        "photo.jpg", content or jpeg_with_gps(size=(900, 600)), content_type="image/jpeg"
    )
    return api.post(
        reverse("pro-booking-photos", args=[booking.public_id]),
        {"phase": phase, "file": file, **extra},
        format="multipart",
        HTTP_IDEMPOTENCY_KEY=key_value,
    )


def test_api_envoi_lecture_et_signalement(api_client, django_capture_on_commit_callbacks):
    scene, booking = on_site()
    pro = bearer(api_client, booking.provider.owner, app="pro")
    client = bearer(api_client, scene.client)
    with django_capture_on_commit_callbacks(execute=True):
        response = post_photo(pro, booking)
    data = response.json()
    assert response.status_code == 201 and data["phase"] == "before"
    pattern = rf"^http://storage\.test/bookings/{booking.public_id}/{data['public_id']}"
    assert re.match(pattern + r"\.webp\?", data["url"])
    assert "-thumb.webp" not in data["url"] and data["expires_at"]
    assert (data["width"], data["height"]) == (900, 600)
    # Rejeu : 200, même photo, rien de plus.
    again = post_photo(pro, booking)
    assert (again.status_code, again.json()["public_id"]) == (200, data["public_id"])
    assert BookingPhoto.objects.count() == 1
    # Miniature prête : les deux vues la donnent en premier.
    for api, name in ((client, "booking-detail"), (pro, "pro-booking-detail")):
        detail = api.get(reverse(name, args=[booking.public_id])).json()
        (photo,) = detail["photos"]
        assert re.match(pattern + r"-thumb\.webp\?", photo["thumb_url"])
        assert re.match(pattern + r"\.webp\?", photo["url"]) and photo["status"] == "ready"
    report = client.post(
        reverse("booking-photo-report", args=[booking.public_id, data["public_id"]])
    )
    assert report.status_code == 200 and report.json()["photos"] == []
    assert pro.get(reverse("pro-booking-detail", args=[booking.public_id])).json()["photos"] == []
    assert (
        client.post(
            reverse("booking-photo-report", args=[booking.public_id, data["public_id"]])
        ).status_code
        == 200
    )  # rejeu


def test_api_les_photos_sont_dans_le_detail_de_la_demande(api_client):
    scene, booking = on_site()
    upload(booking)
    detail = bearer(api_client, scene.client).get(
        reverse("request-detail", args=[scene.request.public_id])
    )
    assert detail.status_code == 200
    assert len(detail.json()["booking"]["photos"]) == 1


def test_api_erreurs_d_envoi(api_client, settings):
    scene, booking = on_site()
    pro = bearer(api_client, booking.provider.owner, app="pro")
    response = post_photo(pro, booking, content=b"pas une image")
    assert (response.status_code, response.json()["code"]) == (422, "photo_invalid")
    response = post_photo(pro, booking, phase="pendant")
    assert (response.status_code, response.json()["code"]) == (400, "invalid")
    response = pro.post(
        reverse("pro-booking-photos", args=[booking.public_id]),
        {"phase": "before"},
        format="multipart",
        HTTP_IDEMPOTENCY_KEY=KEY,
    )
    assert response.status_code == 400  # pas de fichier
    response = post_photo(pro, booking, key_value="")
    assert (response.status_code, response.json()["code"]) == (400, "idempotency_key_required")
    settings.BOOKING_PHOTO_MAX_BYTES = 100
    response = post_photo(pro, booking)
    assert (response.status_code, response.json()["code"]) == (413, "photo_too_large")
    settings.BOOKING_PHOTO_MAX_BYTES = 8 * 1024 * 1024
    settings.BOOKING_PHOTO_MAX_PER_PHASE = 1
    assert post_photo(pro, booking).status_code == 201
    response = post_photo(pro, booking, key_value=key(9), content=jpeg_with_gps(size=(333, 200)))
    assert (response.status_code, response.json()["code"]) == (409, "photo_limit_reached")
    response = post_photo(pro, booking, content=jpeg_with_gps(size=(444, 200)))
    assert (response.status_code, response.json()["code"]) == (409, "idempotency_key_reused")
    assert scene.client


def test_api_envoi_refuse_au_client_a_un_autre_pro_et_sans_session(api_client):
    scene, booking = on_site()
    assert post_photo(bearer(api_client, scene.client), booking).status_code == 403
    stranger = bearer(api_client, VerifiedProviderFactory().owner, app="pro")
    assert post_photo(stranger, booking).status_code == 404
    api_client.credentials()
    assert post_photo(api_client, booking).status_code == 401


def test_api_signalement_refuse_a_un_autre_compte(api_client):
    scene, booking = on_site()
    photo = upload(booking).photo
    url = reverse("booking-photo-report", args=[booking.public_id, photo.public_id])
    assert bearer(api_client, CompleteUserFactory()).post(url).status_code == 404
    assert bearer(api_client, booking.provider.owner, app="pro").post(url).status_code == 404
    api_client.credentials()
    assert api_client.post(url).status_code == 401
    assert scene.client
