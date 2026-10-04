"""demo_pro étendu (spec 004) : le parcours complet, par les services, en local seulement."""

import io
from datetime import timedelta
from io import StringIO

import pytest
from django.core.management import CommandError, call_command
from django.utils import timezone
from PIL import Image

from jeflink.bookings import services
from jeflink.bookings.models import Booking, BookingPhoto
from jeflink.bookings.tests.factories import make_scene
from jeflink.common import storage
from jeflink.providers.models import Provider
from jeflink.reviews.models import Review

pytestmark = pytest.mark.django_db


def run(*args):
    out = StringIO()
    call_command("demo_pro", *args, stdout=out)
    return out.getvalue()


@pytest.fixture
def booking(settings):
    """Une réservation confirmée par un pro de démonstration."""
    settings.DJANGO_ENV = "local"
    scene = make_scene(pros=1)
    Provider.objects.filter(pk=scene.providers[0].pk).update(is_demo=True)
    created = services.create_from_quote(quote=scene.quotes[0], actor=scene.client)
    run("confirm", str(created.booking.public_id))
    now = timezone.now()  # le créneau a commencé : « en route » est permis
    Booking.objects.filter(pk=created.booking.pk).update(
        slot_start=now - timedelta(hours=1), slot_end=now + timedelta(hours=3)
    )
    created.booking.refresh_from_db()
    return scene, created.booking


def test_parcours_de_bout_en_bout(booking):
    scene, item = booking
    ref = str(item.public_id)
    assert "completion_code.sms" in run("en-route", ref)
    assert "on_site" in run("arrive", ref)
    assert "EXIF et GPS retirés" in run("start", ref, "--photo")
    item.refresh_from_db()
    assert item.status == "in_progress"
    out = run("amend", ref, "--total", "22000")
    assert "15000 → 22000" in out
    amendment = item.amendments.get()
    services.accept_amendment(
        amendment=amendment, actor=scene.client, total_xof=amendment.total_xof, confirm=True
    )  # le client, sur le web
    code = services.visible_completion_code(Booking.objects.get(pk=item.pk))
    assert "completed" in run("complete", ref, "--code", code, "--photo")
    item.refresh_from_db()
    assert (item.amount_xof, item.completion_method) == (22_000, "code")
    # Photos : stockées sans EXIF ni GPS, miniature prête.
    for photo in BookingPhoto.objects.all():
        stored = Image.open(io.BytesIO(storage.read(photo.image_key)))
        assert stored.format == "WEBP" and len(stored.getexif()) == 0
        assert photo.status == "ready"
    assert BookingPhoto.objects.filter(phase="before").exists()
    assert BookingPhoto.objects.filter(phase="after").exists()
    # Clôture puis avis.
    Booking.objects.filter(pk=item.pk).update(
        dispute_deadline=timezone.now() - timedelta(minutes=1)
    )
    assert services.close_due() == 1
    from jeflink.reviews.services import submit_review

    submit_review(booking=item, actor=scene.client, rating=5, tags=["on_time"], comment="")
    assert Review.objects.get().published_at is not None


def test_fin_sans_code_et_refus_hors_local(booking, settings):
    _, item = booking
    ref = str(item.public_id)
    run("arrive", ref)
    run("start", ref, "--pending")
    assert "no_code" in run("complete", ref, "--no-code", "client_absent", "--photo")
    settings.DJANGO_ENV = "test"
    with pytest.raises(CommandError, match="refusée hors"):
        run("en-route", ref)


def test_une_erreur_metier_devient_une_erreur_de_commande(booking):
    _, item = booking
    with pytest.raises(CommandError, match="before_photos_required"):
        run("arrive", str(item.public_id))
        run("start", str(item.public_id))
