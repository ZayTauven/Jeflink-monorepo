"""Console, lot 2 : rôles de l'équipe, catalogue (métiers, quartiers), réglages, équipe."""

import pytest
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from jeflink.accounts.models import ProProfile, User
from jeflink.catalog.models import Trade, Zone
from jeflink.console.models import AuditLog, PlatformSettings
from jeflink.jobs import services

pytestmark = pytest.mark.django_db
PASSWORD = "un-mot-de-passe-solide"


def as_user(user):
    client = APIClient()
    token, _ = Token.objects.get_or_create(user=user)
    client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
    return client


def staff(role: str, email: str | None = None) -> User:
    return User.objects.create_user(
        email or f"{role}@jeflink.local", PASSWORD, is_staff=True, staff_role=role
    )


@pytest.fixture
def team():
    return {r: staff(r) for r in ("super", "ops", "marketing", "finance")}


@pytest.fixture
def catalog():
    trade = Trade.objects.create(slug="plomberie", name="Plomberie")
    zone = Zone.objects.create(slug="ouakam", name="Ouakam")
    return trade, zone


def actions():
    return list(AuditLog.objects.order_by("id").values_list("action", flat=True))


# --- Rôles -------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "role,allowed,denied",
    [
        ("super", ["overview/", "requests/", "trades/", "team/", "settings/"], []),
        ("ops", ["overview/", "requests/", "trades/", "audit/"], ["team/", "settings/"]),
        ("marketing", ["overview/", "trades/", "zones/"], ["requests/", "pros/", "team/"]),
        ("finance", ["overview/", "badges/"], ["trades/", "requests/", "settings/"]),
    ],
)
def test_chaque_role_voit_ses_rubriques(team, role, allowed, denied):
    api = as_user(team[role])
    for path in allowed:
        assert api.get(f"/api/console/{path}").status_code == 200, path
    for path in denied:
        assert api.get(f"/api/console/{path}").status_code == 403, path


def test_me_donne_le_role_et_les_rubriques(team):
    me = as_user(team["marketing"]).get("/api/auth/me/").data
    assert me["console_role"] == "marketing"
    assert me["console_sections"] == ["dashboard", "catalog", "marketing"]
    client = User.objects.create_user("awa@example.com", PASSWORD)
    assert as_user(client).get("/api/auth/me/").data["console_sections"] == []


def test_un_staff_sans_role_est_aux_operations():
    member = User.objects.create_user("ancien@jeflink.local", PASSWORD, is_staff=True)
    assert member.console_role == "ops"


# --- Catalogue ---------------------------------------------------------------------------------


def test_creer_un_metier(team, catalog):
    api = as_user(team["marketing"])
    res = api.post(
        "/api/console/trades/",
        {
            "name": "Plomberie",
            "services": "Fuite\n- Débouchage\n\nFuite",
            "starting_price": "5 000 F CFA",
            "icon": "bi-droplet",
            "is_active": "1",
        },
    )
    assert res.status_code == 201, res.data
    assert res.data["slug"] == "plomberie-2"  # unique
    assert res.data["services"] == ["Fuite", "Débouchage"]
    assert res.data["starting_price"] == 5000  # entier F CFA
    assert actions() == ["trade.create"]


def test_icone_et_image_controlees(team):
    api = as_user(team["super"])
    assert api.post("/api/console/trades/", {"name": "X", "icon": "<script>"}).status_code == 400
    res = api.post("/api/console/trades/", {"name": "X", "image": "https://ailleurs.example/x.png"})
    assert res.status_code == 400


def test_desactiver_un_metier_le_retire_du_site(team, catalog):
    trade, zone = catalog
    api = as_user(team["ops"])
    url = f"/api/console/trades/{trade.pk}/update/"
    res = api.post(url, {"name": "Plomberie", "is_active": "0"})
    assert res.status_code == 200 and res.data["is_active"] is False
    assert APIClient().get("/api/trades/").data == []
    assert AuditLog.objects.get().details == "is_active"
    assert (
        api.post(url, {"name": "Plomberie", "is_active": "0"}).status_code == 400
    )  # rien à changer
    client = User.objects.create_user("awa@example.com", PASSWORD)
    trade.refresh_from_db()
    with pytest.raises(Exception, match="pas ouvert"):
        services.create_request(client, trade=trade, zone=zone, title="x", description="…")


def test_quartiers(team, catalog):
    api = as_user(team["marketing"])
    assert api.post("/api/console/zones/", {"name": "ouakam", "city": "Dakar"}).status_code == 400
    res = api.post("/api/console/zones/", {"name": "Rufisque", "city": "Rufisque"})
    assert res.status_code == 201 and res.data["slug"] == "rufisque"
    zone_id = res.data["id"]
    api.post(f"/api/console/zones/{zone_id}/update/", {"name": "Rufisque", "is_active": "0"})
    assert "rufisque" not in [z["slug"] for z in APIClient().get("/api/zones/").data]


# --- Réglages ----------------------------------------------------------------------------------


def settings_form(**changes):
    form = {
        "max_quotes": 3,
        "stale_after_hours": 24,
        "accepting_requests": "1",
        "closed_message": "",
        "support_whatsapp": "",
        "support_email": "",
    }
    return {**form, **changes}


def test_reglages_reserves_au_super_admin(team):
    assert as_user(team["ops"]).post("/api/console/settings/", settings_form()).status_code == 403


def test_devis_maximum_reglable(team, catalog):
    trade, zone = catalog
    as_user(team["super"]).post("/api/console/settings/", settings_form(max_quotes=1))
    client = User.objects.create_user("awa@example.com", PASSWORD)
    pros = []
    for i in range(2):
        pro = User.objects.create_user(f"pro{i}@example.com", PASSWORD, role=User.Role.PRO)
        ProProfile.objects.create(user=pro, is_verified=True).trades.add(trade)
        pros.append(pro)
    req = services.create_request(client, trade=trade, zone=zone, title="x", description="…")
    services.submit_quote(pros[0], req, 5000)
    with pytest.raises(Exception, match="déjà reçu 1 devis"):
        services.submit_quote(pros[1], req, 4000)
    assert as_user(client).get(f"/api/requests/{req.pk}/").data["quotes_max"] == 1


def test_pause_des_nouvelles_demandes(team, catalog):
    res = as_user(team["super"]).post(
        "/api/console/settings/",
        settings_form(accepting_requests="0", closed_message="Pause pour la Tabaski."),
    )
    assert res.status_code == 200 and res.data["accepting_requests"] is False
    assert APIClient().get("/api/site/").data["closed_message"] == "Pause pour la Tabaski."
    client = User.objects.create_user("awa@example.com", PASSWORD)
    res = as_user(client).post(
        "/api/requests/",
        {"trade": "plomberie", "zone": "ouakam", "title": "Fuite", "description": "…"},
        format="json",
    )
    assert res.status_code == 400
    assert "Tabaski" in str(res.data)
    assert actions() == ["settings.update"]


def test_whatsapp_du_support_normalise(team):
    api = as_user(team["super"])
    res = api.post("/api/console/settings/", settings_form(support_whatsapp="77 123 45 67"))
    assert res.data["support_whatsapp"] == "+221771234567"
    assert PlatformSettings.load().support_whatsapp == "+221771234567"
    bad = api.post("/api/console/settings/", settings_form(support_whatsapp="123"))
    assert bad.status_code == 400


# --- Équipe ------------------------------------------------------------------------------------


def test_ajouter_un_membre(team):
    api = as_user(team["super"])
    res = api.post(
        "/api/console/team/",
        {
            "email": "Fatou@Jeflink.local",
            "first_name": "Fatou",
            "role": "finance",
            "password": "un-provisoire-solide",
        },
    )
    assert res.status_code == 201 and res.data["role"] == "finance"
    login = APIClient().post(
        "/api/auth/login/",
        {"email": "fatou@jeflink.local", "password": "un-provisoire-solide"},
        format="json",
    )
    assert login.status_code == 200
    assert login.data["user"]["console_sections"] == ["dashboard", "finance"]
    weak = api.post(
        "/api/console/team/",
        {"email": "x@jeflink.local", "first_name": "X", "role": "ops", "password": "1234567890"},
    )
    assert weak.status_code == 400  # mot de passe trop simple


def test_regles_de_l_equipe(team):
    sup, ops = team["super"], team["ops"]
    api = as_user(sup)
    assert api.post(f"/api/console/team/{sup.pk}/role/", {"role": "ops"}).status_code == 400
    assert api.post(f"/api/console/team/{sup.pk}/deactivate/").status_code == 400  # soi-même
    res = api.post(f"/api/console/team/{ops.pk}/role/", {"role": "marketing"})
    assert res.data["role"] == "marketing"
    ops_api = as_user(ops)
    assert api.post(f"/api/console/team/{ops.pk}/deactivate/").data["is_active"] is False
    assert ops_api.get("/api/auth/me/").status_code == 401  # déconnecté
    assert actions() == ["team.role", "team.deactivate"]


def test_garder_un_super_admin(team):
    other = staff("super", "autre-super@jeflink.local")
    api = as_user(other)
    assert api.post(f"/api/console/team/{team['super'].pk}/deactivate/").status_code == 200
    # Plus qu'un super admin actif : « other » ne peut pas perdre ce rôle via un tiers.
    team["super"].is_active = True
    team["super"].save()
    as_user(team["super"]).post(f"/api/console/team/{other.pk}/role/", {"role": "ops"})
    assert User.objects.get(pk=other.pk).console_role == "ops"
    res = as_user(other).post(f"/api/console/team/{team['super'].pk}/role/", {"role": "ops"})
    assert res.status_code == 403  # « other » n'est plus super admin


# --- Retours de la revue sécurité --------------------------------------------------------------


def test_tableau_de_bord_sans_donnees_des_operations_pour_marketing(team):
    data = as_user(team["marketing"]).get("/api/console/overview/").data
    assert "alerts" not in data and "activity" not in data and "top_pros" not in data
    assert "current" in data  # les chiffres globaux restent
    assert "alerts" in as_user(team["ops"]).get("/api/console/overview/").data


def test_un_superuser_django_ne_perd_pas_son_acces_par_la_console(team):
    root = User.objects.create_superuser("root@jeflink.local", PASSWORD)
    res = as_user(team["super"]).post(f"/api/console/team/{root.pk}/deactivate/")
    assert res.status_code == 400
    assert User.objects.get(pk=root.pk).is_active


def test_un_compte_de_l_equipe_ne_se_gere_pas_par_les_pros(team, catalog):
    member = team["marketing"]
    ProProfile.objects.create(user=member)
    api = as_user(team["ops"])
    assert member.pk not in [
        p["account"]["id"] for p in api.get("/api/console/pros/").data["results"]
    ]
    assert api.post(f"/api/console/pros/{member.pk}/verify/").status_code == 404


def test_mot_de_passe_provisoire_different_de_l_identite(team):
    res = as_user(team["super"]).post(
        "/api/console/team/",
        {
            "email": "mamadoundiaye@jeflink.local",
            "first_name": "Mamadou",
            "last_name": "Ndiaye",
            "role": "ops",
            "password": "mamadoundiaye",
        },
    )
    assert res.status_code == 400 and "password" in res.data


def test_le_journal_de_l_equipe_reste_aux_super_admins(team):
    sup = as_user(team["super"])
    sup.post(f"/api/console/team/{team['finance'].pk}/role/", {"role": "marketing"})
    assert as_user(team["ops"]).get("/api/console/audit/").data["count"] == 0
    assert sup.get("/api/console/audit/").data["count"] == 1
