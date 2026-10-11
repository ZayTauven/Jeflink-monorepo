"""Parcours complet de la démo et règles qui protègent la confiance."""

import pytest
from rest_framework.test import APIClient

from jeflink.accounts.models import ProProfile, User
from jeflink.catalog.models import Trade, Zone

pytestmark = pytest.mark.django_db
PASSWORD = "un-mot-de-passe-solide"


@pytest.fixture
def catalog():
    trade = Trade.objects.create(slug="plomberie", name="Plomberie")
    zone = Zone.objects.create(slug="ouakam", name="Ouakam")
    return trade, zone


def register(**data):
    client = APIClient()
    payload = {"password": PASSWORD, "first_name": "Test", **data}
    res = client.post("/api/auth/register/", payload, format="json")
    assert res.status_code == 201, res.data
    client.credentials(HTTP_AUTHORIZATION=f"Token {res.data['token']}")
    return client, User.objects.get(email=data["email"].lower())


def verified_pro(email, catalog):
    client, user = register(
        email=email, role="pro", trades=[catalog[0].slug], zones=[catalog[1].slug]
    )
    ProProfile.objects.filter(user=user).update(is_verified=True)
    return client, user


def publish(client):
    res = client.post(
        "/api/requests/",
        {"trade": "plomberie", "zone": "ouakam", "title": "Fuite", "description": "Sous l'évier"},
        format="json",
    )
    assert res.status_code == 201, res.data
    return res.data["id"]


def test_login_par_email_et_mot_de_passe():
    register(email="Awa@Example.com", phone="77 123 45 67")
    user = User.objects.get(email="awa@example.com")
    assert user.phone == "+221771234567"
    res = APIClient().post(
        "/api/auth/login/", {"email": "awa@example.com", "password": PASSWORD}, format="json"
    )
    assert res.status_code == 200 and res.data["token"]
    bad = APIClient().post(
        "/api/auth/login/", {"email": "awa@example.com", "password": "x"}, format="json"
    )
    assert bad.status_code == 400


def test_parcours_complet(catalog):
    awa, _ = register(email="awa@example.com")
    pro, pro_user = verified_pro("pro@example.com", catalog)
    req_id = publish(awa)

    assert [r["id"] for r in pro.get("/api/requests/?scope=open").data] == [req_id]
    res = pro.post(f"/api/requests/{req_id}/quotes/", {"amount": 15000}, format="json")
    assert res.status_code == 201

    detail = awa.get(f"/api/requests/{req_id}/").data
    assert detail["actions"] == ["accept", "cancel"]
    assert detail["contact_phone"] is None
    quote_id = detail["quotes"][0]["id"]

    res = awa.post(f"/api/requests/{req_id}/accept/", {"quote_id": quote_id}, format="json")
    assert res.data["status"] == "booked" and res.data["pro"]["id"] == pro_user.pk

    assert pro.post(f"/api/requests/{req_id}/complete/").data["status"] == "done"
    res = awa.post(f"/api/requests/{req_id}/review/", {"rating": 5}, format="json")
    assert res.status_code == 201

    events = [e["status"] for e in awa.get(f"/api/requests/{req_id}/").data["events"]]
    assert events == ["open", "booked", "done"]
    assert APIClient().get(f"/api/pros/{pro_user.pk}/").data["rating"] == {
        "average": 5.0,
        "count": 1,
    }


def test_un_client_ne_voit_pas_les_demandes_des_autres(catalog):
    awa, _ = register(email="awa@example.com")
    moussa, _ = register(email="moussa@example.com")
    req_id = publish(awa)
    assert moussa.get(f"/api/requests/{req_id}/").status_code == 404
    assert moussa.get("/api/requests/").data == []


def test_pro_non_verifie_ne_peut_pas_chiffrer(catalog):
    awa, _ = register(email="awa@example.com")
    pro, _ = register(email="pro@example.com", role="pro", trades=["plomberie"])
    req_id = publish(awa)
    res = pro.post(f"/api/requests/{req_id}/quotes/", {"amount": 10000}, format="json")
    assert res.status_code == 403


def test_trois_devis_maximum(catalog):
    awa, _ = register(email="awa@example.com")
    req_id = publish(awa)
    for i in range(3):
        pro, _ = verified_pro(f"pro{i}@example.com", catalog)
        assert (
            pro.post(f"/api/requests/{req_id}/quotes/", {"amount": 9000}, format="json").status_code
            == 201
        )
    late, _ = verified_pro("late@example.com", catalog)
    assert (
        late.post(f"/api/requests/{req_id}/quotes/", {"amount": 8000}, format="json").status_code
        == 400
    )


def test_transition_interdite(catalog):
    awa, _ = register(email="awa@example.com")
    req_id = publish(awa)
    assert awa.post(f"/api/requests/{req_id}/cancel/").data["status"] == "cancelled"
    assert awa.post(f"/api/requests/{req_id}/complete/").status_code == 400


def test_un_pro_ne_publie_pas_de_demande(catalog):
    pro, _ = verified_pro("pro@example.com", catalog)
    res = pro.post(
        "/api/requests/",
        {"trade": "plomberie", "zone": "ouakam", "title": "x", "description": "y"},
        format="json",
    )
    assert res.status_code == 403
