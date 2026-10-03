"""API des réservations côté client (spec 003) : accepter, lire, annuler."""

from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from jeflink.accounts.tests.factories import CompleteUserFactory, UserFactory
from jeflink.bookings.machine import DISCLOSED_STATUSES
from jeflink.bookings.models import Booking
from jeflink.bookings.tests.factories import accept, confirm, make_scene
from jeflink.requests.models import Quote, ServiceRequest
from jeflink.requests.tests.factories import ServiceRequestFactory
from jeflink.requests.tests.test_requests_api import bearer

pytestmark = pytest.mark.django_db


def accept_url(quote):
    return reverse("quote-accept", args=[quote.public_id])


# --- POST /api/quotes/{id}/accept/ -------------------------------------------------------------


def test_accepter_un_devis_201_sans_numero(api_client):
    scene = make_scene(pros=2)
    api = bearer(api_client, scene.client)
    response = api.post(accept_url(scene.quotes[1]))
    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "accepted" and data["contact"] is None
    assert data["amount_xof"] == scene.quotes[1].total_xof
    assert data["payment"] == "direct_to_pro"
    assert data["confirm_deadline"] and data["provider"]["business_name"]
    assert data["request"] == str(scene.request.public_id)
    assert scene.providers[1].owner.phone not in response.content.decode()
    assert "id" not in data and "client" not in data


def test_rejouer_l_acceptation_200_meme_reservation(api_client):
    scene = make_scene()
    api = bearer(api_client, scene.client)
    first = api.post(accept_url(scene.quotes[0]))
    again = api.post(accept_url(scene.quotes[0]))
    assert (first.status_code, again.status_code) == (201, 200)
    assert first.json()["public_id"] == again.json()["public_id"]
    assert Booking.objects.count() == 1


def test_un_deuxieme_devis_409(api_client):
    scene = make_scene(pros=2)
    api = bearer(api_client, scene.client)
    api.post(accept_url(scene.quotes[0]))
    response = api.post(accept_url(scene.quotes[1]))
    assert (response.status_code, response.json()["code"]) == (409, "quote_not_available")


def test_devis_echu_409(api_client):
    scene = make_scene()
    Quote.objects.filter(pk=scene.quotes[0].pk).update(
        valid_until=timezone.now() - timedelta(minutes=1)
    )
    response = bearer(api_client, scene.client).post(accept_url(scene.quotes[0]))
    assert (response.status_code, response.json()["code"]) == (409, "quote_not_available")


def test_devis_d_un_autre_client_404_sans_session_401_invite_403(api_client):
    scene = make_scene()
    other = bearer(api_client, CompleteUserFactory()).post(accept_url(scene.quotes[0]))
    assert (other.status_code, other.json()["code"]) == (404, "not_found")
    assert not Booking.objects.exists()
    api_client.credentials()
    assert api_client.post(accept_url(scene.quotes[0])).status_code == 401
    guest = UserFactory()
    ServiceRequest.objects.filter(pk=scene.request.pk).update(client=guest)
    response = bearer(api_client, guest).post(accept_url(scene.quotes[0]))
    assert (response.status_code, response.json()["code"]) == (403, "profile_incomplete")


def test_devis_inconnu_404(api_client):
    import uuid

    response = bearer(api_client, CompleteUserFactory()).post(
        reverse("quote-accept", args=[uuid.uuid4()])
    )
    assert response.status_code == 404


# --- GET /api/bookings/ ------------------------------------------------------------------------


def test_liste_et_detail_de_mes_reservations(api_client):
    scene = make_scene()
    booking = accept(scene)
    ServiceRequestFactory()  # une autre demande, d'un autre client
    api = bearer(api_client, scene.client)
    listing = api.get(reverse("bookings")).json()
    assert [b["public_id"] for b in listing["results"]] == [str(booking.public_id)]
    detail = api.get(reverse("booking-detail", args=[booking.public_id]))
    assert detail.status_code == 200 and detail.json()["trade"]["slug"] == scene.trade.slug


def test_reservation_d_un_autre_client_404_et_sans_session_401(api_client):
    booking = accept(make_scene())
    other = bearer(api_client, CompleteUserFactory())
    for response in (
        other.get(reverse("booking-detail", args=[booking.public_id])),
        other.post(reverse("booking-cancel", args=[booking.public_id]), {"reason": "price"},
                   format="json"),
    ):  # fmt: skip
        assert (response.status_code, response.json()["code"]) == (404, "not_found")
    assert other.get(reverse("bookings")).json()["results"] == []
    api_client.credentials()
    assert api_client.get(reverse("bookings")).status_code == 401


@pytest.mark.parametrize("status", Booking.Status.values)
def test_numero_du_pro_divulgue_seulement_aux_statuts_prevus(api_client, status):
    scene = make_scene(pros=1)
    booking = accept(scene)
    Booking.objects.filter(pk=booking.pk).update(
        status=status, cancelled_by="system" if status == "cancelled" else ""
    )
    response = bearer(api_client, scene.client).get(
        reverse("booking-detail", args=[booking.public_id])
    )
    contact = response.json()["contact"]
    if status in DISCLOSED_STATUSES:
        assert contact == {
            "business_name": scene.providers[0].business_name,
            "phone": scene.providers[0].owner.phone,
        }
    else:
        assert contact is None
        assert scene.providers[0].owner.phone not in response.content.decode()


def test_confirmee_montre_le_numero_du_pro(api_client):
    scene = make_scene(pros=1)
    booking = accept(scene)
    confirm(booking)
    data = (
        bearer(api_client, scene.client)
        .get(reverse("booking-detail", args=[booking.public_id]))
        .json()
    )
    assert data["status"] == "scheduled" and data["contact"]["phone"]


# --- POST /api/bookings/{id}/cancel/ -----------------------------------------------------------


def test_le_client_annule_200(api_client):
    scene = make_scene(pros=2)
    booking = accept(scene, 0)
    api = bearer(api_client, scene.client)
    response = api.post(
        reverse("booking-cancel", args=[booking.public_id]),
        {"reason": "found_other"},
        format="json",
    )
    assert response.status_code == 200
    assert (response.json()["status"], response.json()["cancelled_by"]) == ("cancelled", "client")
    assert response.json()["contact"] is None
    again = api.post(
        reverse("booking-cancel", args=[booking.public_id]), {"reason": "price"}, format="json"
    )
    assert (again.status_code, again.json()["code"]) == (409, "transition_not_allowed")


@pytest.mark.parametrize(
    ("data", "code", "status"),
    [
        ({"reason": "too_far"}, "reason_invalid", 422),
        ({"reason": "other"}, "note_invalid", 422),
        ({"reason": "other", "note": "Appelez le 77 123 45 67"}, "note_invalid", 422),
        ({}, "invalid", 400),
    ],
)
def test_annulation_invalide(api_client, data, code, status):
    scene = make_scene(pros=1)
    booking = accept(scene)
    api = bearer(api_client, scene.client)
    response = api.post(reverse("booking-cancel", args=[booking.public_id]), data, format="json")
    assert (response.status_code, response.json()["code"]) == (status, code)
    booking.refresh_from_db()
    assert booking.status == "accepted"
