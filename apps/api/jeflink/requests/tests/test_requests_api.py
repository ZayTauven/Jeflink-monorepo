"""API de la demande, des devis et de « Mes demandes » (spec 003) : autorisé, refusé, invalide."""

from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from jeflink.accounts.sessions import create_session
from jeflink.accounts.tests.factories import CompleteUserFactory, UserFactory
from jeflink.analytics.models import UnservedDemand
from jeflink.bookings.tests.factories import accept, confirm, make_scene
from jeflink.catalog.tests.factories import ServiceFactory, TradeFactory
from jeflink.requests.models import ServiceRequest
from jeflink.requests.tests.factories import ServiceRequestFactory
from jeflink.zones.tests.factories import ZoneFactory

pytestmark = pytest.mark.django_db
KEY = "api-key-" + "0" * 24


def bearer(api_client, user, app="client"):
    """Un client HTTP neuf par utilisateur : plusieurs comptes peuvent parler dans un test."""
    pair = create_session(user=user, app=app, platform="android")
    api = APIClient()
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {pair.access}")
    return api


def post(api_client, url, data, key=KEY):
    return api_client.post(url, data, format="json", HTTP_IDEMPOTENCY_KEY=key)


@pytest.fixture
def catalog():
    trade = TradeFactory(slug="plomberie", name_fr="Plomberie")
    ServiceFactory(trade=trade, slug="fuite", name_fr="Fuite", urgent=True)
    zone = ZoneFactory(slug="ouakam", name="Ouakam", trades=[trade])
    return {"trade": trade, "zone": zone}


def body(**overrides):
    base = {
        "trade_slug": "plomberie",
        "zone_slug": "ouakam",
        "landmark": "près de la boutique, portail bleu",
        "description": "Fuite sous l'évier",
    }
    return {**base, **overrides}


# --- POST /api/requests/ ------------------------------------------------------------------------


def test_creation_201_avec_le_detail(api_client, catalog):
    client = CompleteUserFactory()
    response = post(bearer(api_client, client), reverse("requests"), body())
    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "open" and data["channel"] == "app"
    assert data["trade"]["slug"] == "plomberie" and data["trade"]["name"] == {
        "fr": "Plomberie",
        "wo": None,
    }
    assert data["zone"] == {"slug": "ouakam", "name": "Ouakam"}
    assert data["landmark"] and data["has_location"] is False
    assert data["quotes"] == [] and data["booking"] is None
    assert "client" not in data and "idempotency_key" not in data and "id" not in data


def test_rejeu_200_meme_demande(api_client, catalog):
    api = bearer(api_client, CompleteUserFactory())
    first = post(api, reverse("requests"), body())
    again = post(api, reverse("requests"), body())
    assert (first.status_code, again.status_code) == (201, 200)
    assert first.json()["public_id"] == again.json()["public_id"]
    assert ServiceRequest.objects.count() == 1


def test_meme_cle_autre_corps_409(api_client, catalog):
    api = bearer(api_client, CompleteUserFactory())
    post(api, reverse("requests"), body())
    response = post(api, reverse("requests"), body(description="Autre chose"))
    assert (response.status_code, response.json()["code"]) == (409, "idempotency_key_reused")


def test_position_et_zone_ambigue_puis_rejeu(api_client, catalog):
    other = ZoneFactory(slug="ngor", name="Ngor", trades=[catalog["trade"]])
    other.center = catalog["zone"].center
    other.save()
    api = bearer(api_client, CompleteUserFactory())
    point = {"lat": 14.76, "lon": -17.44}
    ambiguous = body(zone_slug=None, location=point, landmark="")
    response = post(api, reverse("requests"), ambiguous)
    assert response.status_code == 422 and response.json()["code"] == "zone_ambiguous"
    assert {c["slug"] for c in response.json()["candidates"]} == {"ouakam", "ngor"}
    assert not ServiceRequest.objects.exists()
    chosen = post(api, reverse("requests"), {**ambiguous, "zone_slug": "ngor"})
    assert chosen.status_code == 201 and chosen.json()["zone"]["slug"] == "ngor"
    assert chosen.json()["has_location"] is True and "location" not in chosen.json()


def test_quartier_inconnu_needs_zone(api_client, catalog):
    response = post(
        bearer(api_client, CompleteUserFactory()),
        reverse("requests"),
        body(zone_slug=None, zone_text="Keur Massar"),
    )
    assert response.status_code == 201
    assert response.json()["status"] == "needs_zone" and response.json()["zone"] is None
    assert response.json()["expires_at"] is None


def test_metier_non_ouvert_422_et_signal(api_client, catalog):
    TradeFactory(slug="electricite")
    response = post(
        bearer(api_client, CompleteUserFactory()),
        reverse("requests"),
        body(trade_slug="electricite"),
    )
    assert (response.status_code, response.json()["code"]) == (422, "trade_not_in_zone")
    assert UnservedDemand.objects.filter(reason="trade_not_in_zone").count() == 1


@pytest.mark.parametrize(
    ("overrides", "code"),
    [
        ({"trade_slug": "inconnu"}, "trade_not_found"),
        ({"zone_slug": "inconnue"}, "zone_not_found"),
        ({"landmark": ""}, "landmark_or_location_required"),
        ({"description": ""}, "description_required"),
        ({"service_slug": "absent"}, "service_not_in_trade"),
        ({"preferred_when": "date", "preferred_date": "2001-01-01"}, "slot_invalid"),
        ({"zone_slug": None}, "zone_required"),
    ],
)
def test_refus_metier_422(api_client, catalog, overrides, code):
    response = post(
        bearer(api_client, CompleteUserFactory()), reverse("requests"), body(**overrides)
    )
    assert (response.status_code, response.json()["code"]) == (422, code)


@pytest.mark.parametrize(
    "overrides",
    [
        {"trade_slug": ""},
        {"description": "x" * 1001},
        {"location": {"lat": 120, "lon": 0}},
        {"preferred_date": "demain"},
        {"urgent": "peut-être"},
    ],
)
def test_corps_invalide_400(api_client, catalog, overrides):
    response = post(
        bearer(api_client, CompleteUserFactory()), reverse("requests"), body(**overrides)
    )
    assert response.status_code == 400 and response.json()["code"] == "invalid"
    assert "fields" in response.json()
    # L'erreur ne recopie jamais la saisie.
    assert "x" * 50 not in response.content.decode()


def test_cle_d_idempotence_obligatoire(api_client, catalog):
    api = bearer(api_client, CompleteUserFactory())
    response = api.post(reverse("requests"), body(), format="json")
    assert (response.status_code, response.json()["code"]) == (400, "idempotency_key_required")


def test_limite_de_trois_demandes_409(api_client, catalog):
    client = CompleteUserFactory()
    for _ in range(3):
        ServiceRequestFactory(client=client)
    response = post(bearer(api_client, client), reverse("requests"), body())
    assert (response.status_code, response.json()["code"]) == (409, "request_limit_reached")


def test_limite_quotidienne_429(api_client, catalog, settings):
    settings.REQUEST_CREATE_DAILY_LIMIT = 1
    api = bearer(api_client, CompleteUserFactory())
    assert post(api, reverse("requests"), body(), key="a" * 30).status_code == 201
    response = post(api, reverse("requests"), body(), key="b" * 30)
    assert (response.status_code, response.json()["code"]) == (429, "request_rate_limited")
    assert response.json()["retry_after"] >= 1


def test_creation_fermee_si_redis_tombe(api_client, catalog, redis_down):
    response = post(bearer(api_client, CompleteUserFactory()), reverse("requests"), body())
    assert response.status_code == 503 and not ServiceRequest.objects.exists()


def test_creation_refusee_sans_session_ou_sans_profil_complet(api_client, catalog):
    assert post(api_client, reverse("requests"), body()).status_code == 401
    guest = UserFactory()  # invité : pas de nom
    response = post(bearer(api_client, guest), reverse("requests"), body())
    assert (response.status_code, response.json()["code"]) == (403, "profile_incomplete")
    assert not ServiceRequest.objects.exists()


# --- GET /api/requests/ et détail --------------------------------------------------------------


def test_liste_paginee_par_curseur_et_limitee_a_mes_demandes(api_client):
    client = CompleteUserFactory()
    for _ in range(25):
        ServiceRequestFactory(client=client)
    ServiceRequestFactory()  # celle d'un autre
    api = bearer(api_client, client)
    page = api.get(reverse("requests")).json()
    assert len(page["results"]) == 20 and page["next"] and page["previous"] is None
    second = api.get(page["next"]).json()
    assert len(second["results"]) == 5 and second["next"] is None
    first = page["results"][0]
    assert set(first) == {
        "public_id", "status", "trade", "service", "zone", "urgent", "created_at", "expires_at",
    }  # fmt: skip
    assert "landmark" not in first and "description" not in first


def test_liste_sans_session_401(api_client):
    assert api_client.get(reverse("requests")).status_code == 401


def test_detail_d_un_autre_client_404(api_client):
    request = ServiceRequestFactory()
    api = bearer(api_client, CompleteUserFactory())
    response = api.get(reverse("request-detail", args=[request.public_id]))
    assert (response.status_code, response.json()["code"]) == (404, "not_found")


def test_detail_embarque_les_devis_tries_par_creneau_et_numeros_masques(api_client):
    scene = make_scene(pros=3)
    first = scene.quotes[0]
    first.message = "Rappelez-moi au 77 123 45 67"
    first.save()
    api = bearer(api_client, scene.client)
    data = api.get(reverse("request-detail", args=[scene.request.public_id])).json()
    assert data["status"] == "quoted" and len(data["quotes"]) == 3
    slots = [q["slot_start"] for q in data["quotes"]]
    assert slots == sorted(slots)
    shown = next(q for q in data["quotes"] if q["public_id"] == str(first.public_id))
    assert "123" not in shown["message"] and "••••" in shown["message"]
    assert shown["provider"]["verified"] is True and shown["provider"]["business_name"]
    assert shown["lines"][0]["kind"] == "labor"
    assert "phone" not in shown["provider"]
    assert data["booking"] is None


def test_detail_une_demande_echue_s_affiche_expiree_sans_la_tache(api_client):
    request = ServiceRequestFactory(expires_at=timezone.now() - timedelta(minutes=1))
    api = bearer(api_client, request.client)
    assert (
        api.get(reverse("request-detail", args=[request.public_id])).json()["status"] == "expired"
    )


def test_detail_embarque_la_reservation_active(api_client):
    scene = make_scene(pros=2)
    booking = accept(scene, 0)
    api = bearer(api_client, scene.client)
    data = api.get(reverse("request-detail", args=[scene.request.public_id])).json()
    assert data["status"] == "booked"
    assert data["booking"]["public_id"] == str(booking.public_id)
    assert data["booking"]["contact"] is None  # pas de numéro avant la confirmation
    assert {q["status"] for q in data["quotes"]} == {"accepted", "held"}
    confirm(booking)
    data = api.get(reverse("request-detail", args=[scene.request.public_id])).json()
    assert data["booking"]["contact"]["phone"] == scene.providers[0].owner.phone


def test_message_du_devis_accepte_demasque_apres_confirmation(api_client):
    scene = make_scene(pros=1)
    scene.quotes[0].message = "Joignable au 77 123 45 67"
    scene.quotes[0].save()
    booking = accept(scene)
    api = bearer(api_client, scene.client)
    url = reverse("request-detail", args=[scene.request.public_id])
    assert "123" not in api.get(url).json()["quotes"][0]["message"]
    confirm(booking)
    assert "77 123 45 67" in api.get(url).json()["quotes"][0]["message"]


# --- POST /api/requests/{id}/cancel/ ------------------------------------------------------------


def test_annulation_200(api_client):
    request = ServiceRequestFactory()
    api = bearer(api_client, request.client)
    response = api.post(
        reverse("request-cancel", args=[request.public_id]),
        {"reason": "changed_mind"},
        format="json",
    )
    assert response.status_code == 200 and response.json()["status"] == "cancelled"


def test_annulation_d_une_demande_reservee_409(api_client):
    scene = make_scene(pros=1)
    accept(scene)
    api = bearer(api_client, scene.client)
    response = api.post(
        reverse("request-cancel", args=[scene.request.public_id]),
        {"reason": "price"},
        format="json",
    )
    assert (response.status_code, response.json()["code"]) == (409, "request_closed")


@pytest.mark.parametrize(
    ("data", "code", "status"),
    [
        ({"reason": "inconnu"}, "reason_invalid", 422),
        ({"reason": "other"}, "note_invalid", 422),
        ({"reason": "other", "note": "Appelez le 77 123 45 67"}, "note_invalid", 422),
        ({}, "invalid", 400),
    ],
)
def test_annulation_invalide(api_client, data, code, status):
    request = ServiceRequestFactory()
    api = bearer(api_client, request.client)
    response = api.post(reverse("request-cancel", args=[request.public_id]), data, format="json")
    assert (response.status_code, response.json()["code"]) == (status, code)


def test_annulation_par_un_autre_404_et_sans_session_401(api_client):
    request = ServiceRequestFactory()
    url = reverse("request-cancel", args=[request.public_id])
    assert api_client.post(url, {"reason": "price"}, format="json").status_code == 401
    api = bearer(api_client, CompleteUserFactory())
    assert api.post(url, {"reason": "price"}, format="json").status_code == 404
    request.refresh_from_db()
    assert request.status == "open"
