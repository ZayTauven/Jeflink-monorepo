"""Contrat de l'API (spec 003) : listes typées, erreur 422, énumérations, désistement du pro."""

import pytest
from django.urls import reverse

from jeflink.accounts.tests.factories import CompleteUserFactory
from jeflink.bookings.machine import Actor
from jeflink.bookings.services import cancel_booking
from jeflink.bookings.tests.factories import accept, make_scene
from jeflink.catalog.tests.factories import TradeFactory
from jeflink.zones.tests.factories import ZoneFactory

from .test_requests_api import bearer, body, post

pytestmark = pytest.mark.django_db


def test_withdrawn_by_provider(api_client):
    scene = make_scene(pros=2)
    api = bearer(api_client, scene.client)
    url = reverse("request-detail", args=[scene.request.public_id])
    assert api.get(url).json()["withdrawn_by_provider"] is False
    booking = accept(scene, 0)
    assert api.get(url).json()["withdrawn_by_provider"] is False  # réservation active
    cancel_booking(
        booking=booking, actor=scene.providers[0].owner, actor_kind=Actor.PRO, reason="too_far"
    )
    data = api.get(url).json()
    assert data["withdrawn_by_provider"] is True and data["status"] == "quoted"
    assert data["booking"] is None and "too_far" not in str(data)


def test_withdrawn_by_provider_faux_si_le_client_annule(api_client):
    scene = make_scene(pros=1)
    booking = accept(scene)
    cancel_booking(booking=booking, actor=scene.client, actor_kind=Actor.CLIENT, reason="price")
    url = reverse("request-detail", args=[scene.request.public_id])
    assert bearer(api_client, scene.client).get(url).json()["withdrawn_by_provider"] is False


def test_enumerations_refusent_une_valeur_inconnue(api_client):
    trade = TradeFactory(slug="plomberie")
    ZoneFactory(slug="ouakam", trades=[trade])
    api = bearer(api_client, CompleteUserFactory())
    for field, value in (("preferred_when", "demain"), ("preferred_period", "nuit")):
        response = post(api, reverse("requests"), body(**{field: value}))
        assert (response.status_code, response.json()["code"]) == (400, "invalid")


def test_schema_listes_typees_et_erreur_422(api_client):
    schema = api_client.get(reverse("schema") + "?format=json").json()
    paths = schema["paths"]
    lists = ("/api/requests/", "/api/bookings/", "/api/pro/requests/", "/api/pro/quotes/")
    for path in (*lists, "/api/pro/bookings/"):
        ok = paths[path]["get"]["responses"]["200"]["content"]["application/json"]["schema"]
        assert "Paginated" in ok["$ref"], path
    created = paths["/api/requests/"]["post"]["responses"]["422"]["content"]["application/json"]
    assert created["schema"]["$ref"].endswith("/ApiError")
    components = schema["components"]["schemas"]
    assert {"code", "candidates"} <= set(components["ApiError"]["properties"])
    assert {"PreferredWhenEnum", "PreferredPeriodEnum"} <= set(components)
