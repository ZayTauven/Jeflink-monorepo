"""API du déroulé (spec 004, tâche 2) : en-route, arrive, start. Autorisé, refusé, invalide."""

from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from jeflink.accounts.tests.factories import CompleteUserFactory
from jeflink.bookings.machine import Status
from jeflink.bookings.models import BookingEvent
from jeflink.providers.models import Provider
from jeflink.providers.tests.factories import VerifiedProviderFactory
from jeflink.requests.tests.test_requests_api import bearer

from .factories import advance, scheduled

pytestmark = pytest.mark.django_db
STEPS = ["pro-booking-en-route", "pro-booking-arrive", "pro-booking-start"]


def url(name, booking):
    return reverse(name, args=[booking.public_id])


def pro_api(api_client, booking):
    return bearer(api_client, booking.provider.owner, app="pro")


def test_le_deroule_complet(api_client):
    scene, booking = scheduled()
    api = pro_api(api_client, booking)
    response = api.post(url("pro-booking-en-route", booking), {}, format="json")
    assert response.status_code == 200
    assert response.json()["status"] == "en_route" and response.json()["en_route_at"]
    assert response.json()["on_site_at"] is None
    response = api.post(url("pro-booking-arrive", booking), {}, format="json")
    assert (response.status_code, response.json()["status"]) == (200, "on_site")
    response = api.post(url("pro-booking-start", booking), {"photos_pending": True}, format="json")
    data = response.json()
    assert (response.status_code, data["status"]) == (200, "in_progress")
    assert data["started_at"] and data["completed_at"] is None and data["dispute_deadline"] is None
    # Le client voit les mêmes étapes horodatées.
    client_data = bearer(api_client, scene.client).get(
        reverse("booking-detail", args=[booking.public_id])
    )
    assert client_data.json()["status"] == "in_progress"
    assert client_data.json()["started_at"] == data["started_at"]


@pytest.mark.parametrize("name", STEPS)
def test_rejouer_repond_200_sans_nouvel_evenement(api_client, name):
    _, booking = scheduled()
    api = pro_api(api_client, booking)
    body = {"photos_pending": True} if name.endswith("start") else {}
    for step in STEPS[: STEPS.index(name) + 1]:
        step_body = {"photos_pending": True} if step.endswith("start") else {}
        assert api.post(url(step, booking), step_body, format="json").status_code == 200
    before = BookingEvent.objects.filter(booking=booking).count()
    response = api.post(url(name, booking), body, format="json")
    assert response.status_code == 200
    assert BookingEvent.objects.filter(booking=booking).count() == before


def test_start_sans_photo_repond_422(api_client):
    _, booking = scheduled()
    api = pro_api(api_client, booking)
    api.post(url("pro-booking-arrive", booking), {}, format="json")
    response = api.post(url("pro-booking-start", booking), {}, format="json")
    assert (response.status_code, response.json()) == (422, {"code": "before_photos_required"})


def test_start_n_est_pas_deduit(api_client):
    _, booking = scheduled()
    response = pro_api(api_client, booking).post(
        url("pro-booking-start", booking), {"photos_pending": True}, format="json"
    )
    assert (response.status_code, response.json()["code"]) == (409, "transition_not_allowed")


@pytest.mark.parametrize("name", STEPS)
def test_refus_client_sans_role_et_non_authentifie(api_client, name):
    scene, booking = scheduled()
    response = bearer(api_client, scene.client).post(url(name, booking), {}, format="json")
    assert (response.status_code, response.json()["code"]) == (403, "role_required")
    api_client.credentials()
    assert api_client.post(url(name, booking), {}, format="json").status_code == 401


@pytest.mark.parametrize("name", STEPS)
def test_un_autre_pro_obtient_404(api_client, name):
    _, booking = scheduled()
    stranger = VerifiedProviderFactory(owner=CompleteUserFactory())
    response = bearer(api_client, stranger.owner, app="pro").post(
        url(name, booking), {}, format="json"
    )
    assert (response.status_code, response.json()["code"]) == (404, "not_found")


@pytest.mark.parametrize("name", STEPS)
def test_un_pro_suspendu_ne_progresse_pas(api_client, name):
    _, booking = scheduled()
    Provider.objects.filter(pk=booking.provider_id).update(status="suspended")
    response = pro_api(api_client, booking).post(url(name, booking), {}, format="json")
    assert (response.status_code, response.json()["code"]) == (403, "provider_not_verified")


def test_occurred_at_invalide(api_client):
    _, booking = scheduled()
    api = pro_api(api_client, booking)
    future = (timezone.now() + timedelta(hours=1)).isoformat()
    response = api.post(url("pro-booking-en-route", booking), {"occurred_at": future}, "json")
    assert (response.status_code, response.json()["code"]) == (422, "occurred_at_invalid")
    response = api.post(url("pro-booking-en-route", booking), {"occurred_at": "hier"}, "json")
    assert (response.status_code, response.json()["code"]) == (400, "invalid")
    ok = timezone.now().isoformat()
    response = api.post(url("pro-booking-en-route", booking), {"occurred_at": ok}, "json")
    assert response.status_code == 200
    assert BookingEvent.objects.filter(booking=booking).latest("id").metadata["occurred_at"]


def test_photos_pending_doit_etre_un_booleen(api_client):
    _, booking = scheduled()
    booking = advance(booking, Status.ON_SITE)
    response = pro_api(api_client, booking).post(
        url("pro-booking-start", booking), {"photos_pending": "peut-etre"}, format="json"
    )
    assert (response.status_code, response.json()["code"]) == (400, "invalid")
