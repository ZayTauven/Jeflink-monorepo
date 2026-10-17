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


def test_profil_pro_sans_envoyer_les_metiers(catalog):
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


def test_metier_ajoute_par_le_pro_valide_par_l_equipe(catalog):
    from jeflink.console.models import AuditLog
    from jeflink.jobs import services

    plomberie, ouakam = catalog
    elec = Trade.objects.create(slug="electricite", name="Électricité")
    clim = Trade.objects.create(slug="clim", name="Clim")
    api, pro = register(email="moussa@example.com", role="pro", trades=["plomberie"])
    ProProfile.objects.filter(user=pro).update(is_verified=True)
    profile = ProProfile.objects.get(user=pro)

    res = api.put(
        "/api/auth/me/",
        {"first_name": "Moussa", "trades": ["plomberie", "electricite", "clim"]},
        format="json",
    )
    assert res.status_code == 200, res.data
    assert res.data["pro_profile"]["trades"] == ["plomberie"]
    assert sorted(res.data["pro_profile"]["pending_trades"]) == ["clim", "electricite"]

    # Tant qu'il n'est pas validé, le pro ne voit ni ne chiffre les demandes de ce métier.
    client, _ = register(email="awa@example.com")
    req = services.create_request(
        User.objects.get(email="awa@example.com"),
        trade=elec,
        zone=ouakam,
        title="Prise",
        description="Plus de courant",
    )
    assert api.post(f"/api/requests/{req.pk}/quotes/", {"amount": 5000}).status_code in (403, 404)

    ops = User.objects.create_user("ops@jeflink.local", PASSWORD, is_staff=True, staff_role="ops")
    staff = APIClient()
    staff.force_authenticate(ops)
    base = f"/api/console/pros/{pro.pk}/trades"
    assert staff.get("/api/console/pros/?status=trades").data["count"] == 1
    assert staff.post(f"{base}/{elec.pk}/approve/").status_code == 200
    assert staff.post(f"{base}/{clim.pk}/refuse/", {"reason": ""}).status_code == 400
    res = staff.post(f"{base}/{clim.pk}/refuse/", {"reason": "Pas d'attestation frigoriste"})
    assert res.status_code == 200 and res.data["pending_trades"] == []
    assert staff.post(f"{base}/{plomberie.pk}/approve/").status_code == 400  # pas demandé
    profile.refresh_from_db()
    assert set(profile.trades.values_list("slug", flat=True)) == {"plomberie", "electricite"}
    assert profile.trade_note.startswith("Clim")
    assert api.post(f"/api/requests/{req.pk}/quotes/", {"amount": 5000}).status_code == 201
    assert list(AuditLog.objects.values_list("action", flat=True).order_by("id")) == [
        "pro.trade_approve",
        "pro.trade_refuse",
    ]

    # Retirer un métier : tout de suite ; tout retirer : refusé.
    api.put("/api/auth/me/", {"first_name": "Moussa", "trades": ["electricite"]}, format="json")
    assert list(profile.trades.values_list("slug", flat=True)) == ["electricite"]
    bad = api.put("/api/auth/me/", {"first_name": "Moussa", "trades": []}, format="json")
    assert bad.status_code == 400
