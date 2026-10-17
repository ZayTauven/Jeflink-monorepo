"""Mon profil : identité, comment me joindre, adresses enregistrées, profil pro."""

import pytest
from rest_framework.test import APIClient

from jeflink.accounts.models import ProProfile, SavedAddress, User
from jeflink.catalog.models import Trade, Zone

pytestmark = pytest.mark.django_db
PASSWORD = "un-mot-de-passe-solide"


@pytest.fixture
def catalog():
    trade = Trade.objects.create(slug="plomberie", name="Plomberie")
    zone = Zone.objects.create(slug="ouakam", name="Ouakam")
    Zone.objects.create(slug="yoff", name="Yoff")
    return trade, zone


def register(**data):
    client = APIClient()
    payload = {"password": PASSWORD, "first_name": "Test", **data}
    res = client.post("/api/auth/register/", payload, format="json")
    assert res.status_code == 201, res.data
    client.credentials(HTTP_AUTHORIZATION=f"Token {res.data['token']}")
    return client, User.objects.get(email=data["email"])


def test_mon_profil_et_comment_me_joindre(catalog):
    api, awa = register(email="awa@example.com")
    res = api.put(
        "/api/auth/me/",
        {
            "first_name": "Awa",
            "last_name": "Diop",
            "phone": "77 123 45 67",
            "contact_pref": "whatsapp",
            "contact_hours": "evening",
            "headline": "ignoré pour un client",
        },
        format="json",
    )
    assert res.status_code == 200, res.data
    assert res.data["phone"] == "+221771234567"
    assert res.data["contact_pref"] == "whatsapp" and res.data["contact_hours"] == "evening"
    bad = api.put("/api/auth/me/", {"first_name": "Awa", "phone": "12"}, format="json")
    assert bad.status_code == 400 and "phone" in bad.data


def test_profil_pro_sans_toucher_aux_metiers(catalog):
    trade, zone = catalog
    api, pro = register(email="moussa@example.com", role="pro", trades=["plomberie"])
    res = api.put(
        "/api/auth/me/",
        {
            "first_name": "Moussa",
            "headline": "Plombier à Ouakam",
            "bio": "15 ans de métier.",
            "years_experience": 15,
            "zones": ["ouakam", "yoff"],
            "trades": [],  # ignoré : les métiers ont leur propre parcours
        },
        format="json",
    )
    assert res.status_code == 200, res.data
    profile = ProProfile.objects.get(user=pro)
    assert profile.headline == "Plombier à Ouakam" and profile.years_experience == 15
    assert set(profile.zones.values_list("slug", flat=True)) == {"ouakam", "yoff"}
    assert list(profile.trades.all()) == [trade]


def test_mes_adresses(catalog):
    api, awa = register(email="awa@example.com")
    _, other = register(email="binta@example.com")
    res = api.post(
        "/api/auth/me/addresses/",
        {"label": "Maison", "zone": "ouakam", "landmark": "Derrière la pharmacie, portail bleu"},
        format="json",
    )
    assert res.status_code == 201, res.data
    assert res.data["zone_name"] == "Ouakam"
    pk = res.data["id"]
    assert api.get("/api/auth/me/").data["addresses"][0]["label"] == "Maison"

    res = api.put(
        f"/api/auth/me/addresses/{pk}/", {"label": "Chez moi", "zone": "yoff"}, format="json"
    )
    assert res.data["zone"] == "yoff"

    # Les adresses d'un autre compte restent introuvables.
    intruder = APIClient()
    intruder.force_authenticate(other)
    assert intruder.delete(f"/api/auth/me/addresses/{pk}/").status_code == 404

    for i in range(SavedAddress.MAX - 1):
        api.post("/api/auth/me/addresses/", {"label": f"A{i}", "zone": "ouakam"}, format="json")
    full = api.post("/api/auth/me/addresses/", {"label": "Trop", "zone": "ouakam"}, format="json")
    assert full.status_code == 400

    assert api.delete(f"/api/auth/me/addresses/{pk}/").status_code == 204
    assert awa.addresses.count() == SavedAddress.MAX - 1


def test_adresse_enregistree_en_publiant_une_demande(catalog):
    api, awa = register(email="awa@example.com")
    body = {
        "trade": "plomberie",
        "zone": "ouakam",
        "title": "Fuite",
        "description": "Sous l'évier",
        "landmark": "Face à la mosquée",
        "save_address": "Maison",
    }
    assert api.post("/api/requests/", body, format="json").status_code == 201
    assert api.post("/api/requests/", body, format="json").status_code == 201  # pas de doublon
    assert list(awa.addresses.values_list("label", "landmark")) == [("Maison", "Face à la mosquée")]


def test_contact_de_l_autre_partie_apres_reservation(catalog):
    client, awa = register(email="awa@example.com", phone="771234567")
    awa.photo, awa.contact_pref = "/media/profils/" + "a" * 32 + ".webp", "whatsapp"
    awa.save()
    pro_api, pro = register(email="moussa@example.com", role="pro", trades=["plomberie"])
    ProProfile.objects.filter(user=pro).update(is_verified=True)
    pro.pro_profile.zones.set([catalog[1]])
    rid = client.post(
        "/api/requests/",
        {"trade": "plomberie", "zone": "ouakam", "title": "Fuite", "description": "Évier"},
        format="json",
    ).data["id"]

    assert pro_api.get(f"/api/requests/{rid}/").data["contact"] is None  # pas avant
    quote = pro_api.post(f"/api/requests/{rid}/quotes/", {"amount": 15000}, format="json").data
    client.post(f"/api/requests/{rid}/accept/", {"quote_id": quote["id"]}, format="json")

    seen_by_pro = pro_api.get(f"/api/requests/{rid}/").data["contact"]
    assert seen_by_pro["photo"] == awa.photo and seen_by_pro["prefers"] == "WhatsApp"
    assert seen_by_pro["hours"] == "Toute la journée"
    assert client.get(f"/api/requests/{rid}/").data["contact"]["name"] == pro.public_name
