"""Lot 3 : argent des missions (commission, remise), codes promo, campagnes, soldes des pros."""

from datetime import datetime, timedelta

import pytest
from django.utils import timezone
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from jeflink.accounts.models import ProProfile, User
from jeflink.catalog.models import Campaign, Trade, Zone
from jeflink.console.models import AuditLog, PlatformSettings
from jeflink.jobs import services
from jeflink.jobs.models import Coupon, ServiceRequest

pytestmark = pytest.mark.django_db
PASSWORD = "un-mot-de-passe-solide"


def as_user(user):
    client = APIClient()
    token, _ = Token.objects.get_or_create(user=user)
    client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
    return client


@pytest.fixture
def world():
    trade = Trade.objects.create(slug="climatisation", name="Froid et climatisation")
    zone = Zone.objects.create(slug="ouakam", name="Ouakam")
    client = User.objects.create_user("awa@example.com", PASSWORD)
    pro = User.objects.create_user("pro@example.com", PASSWORD, role=User.Role.PRO)
    ProProfile.objects.create(user=pro, is_verified=True).trades.add(trade)
    staff = {
        role: User.objects.create_user(
            f"{role}@jeflink.local", PASSWORD, is_staff=True, staff_role=role
        )
        for role in ("super", "ops", "marketing", "finance")
    }
    return {"trade": trade, "zone": zone, "client": client, "pro": pro, **staff}


def booked(world, amount=20000, code=""):
    req = services.create_request(
        world["client"], trade=world["trade"], zone=world["zone"], title="Clim", description="…"
    )
    quote = services.submit_quote(world["pro"], req, amount)
    return services.accept_quote(world["client"], req, quote.pk, code)


# --- Commission --------------------------------------------------------------------------------


def test_les_montants_sont_figes_a_la_reservation(world):
    req = booked(world)
    assert (req.price, req.discount, req.commission_rate, req.commission) == (20000, 0, 10, 2000)
    # Un changement de taux ne touche pas les missions déjà réservées.
    PlatformSettings.objects.update(default_commission_percent=15)
    req.refresh_from_db()
    assert req.commission == 2000
    assert booked(world, 10000).commission == 1500


def test_taux_propre_a_un_metier(world):
    world["trade"].commission_percent = 12
    world["trade"].save()
    assert booked(world, 25000).commission == 3000


def test_la_finance_regle_les_commissions(world):
    api = as_user(world["finance"])
    res = api.post(
        "/api/console/commissions/",
        {"default_commission_percent": "8", f"trade_{world['trade'].pk}": "12"},
    )
    assert res.status_code == 200
    assert res.data["default_commission_percent"] == 8
    assert res.data["trades"][0]["effective"] == 12
    assert (
        api.post("/api/console/commissions/", {"default_commission_percent": "80"}).status_code
        == 400
    )
    assert as_user(world["marketing"]).get("/api/console/commissions/").status_code == 403
    assert AuditLog.objects.get().action == "commission.update"


# --- Codes promo -------------------------------------------------------------------------------


def coupon(**kw):
    data = {"code": "CLIM20", "kind": Coupon.Kind.PERCENT, "value": 20, "max_discount": 3000}
    return Coupon.objects.create(**{**data, **kw})


def test_code_promo_en_pourcentage_plafonne(world):
    coupon()
    req = booked(world, 20000, "clim20")  # casse indifférente
    assert (req.discount, req.commission) == (3000, 2000)  # 20 % = 4 000, plafonné à 3 000
    money = as_user(world["client"]).get(f"/api/requests/{req.pk}/").data["money"]
    assert money == {"price": 20000, "discount": 3000, "coupon": "CLIM20", "client_pays": 17000}
    pro_money = as_user(world["pro"]).get(f"/api/requests/{req.pk}/").data["money"]
    assert pro_money["commission"] == 2000


@pytest.mark.parametrize(
    "kw,amount,message",
    [
        ({"is_active": False}, 20000, "pas reconnu"),
        ({"ends_at": timezone.now() - timedelta(days=1)}, 20000, "expiré"),
        ({"starts_at": timezone.now() + timedelta(days=1)}, 20000, "pas encore"),
        ({"min_amount": 30000}, 20000, "au moins 30"),
    ],
)
def test_code_promo_refuse_avec_un_motif(world, kw, amount, message):
    coupon(**kw)
    req = services.create_request(
        world["client"], trade=world["trade"], zone=world["zone"], title="Clim", description="…"
    )
    quote = services.submit_quote(world["pro"], req, amount)
    res = as_user(world["client"]).post(
        f"/api/requests/{req.pk}/accept/", {"quote_id": quote.pk, "coupon": "CLIM20"}
    )
    assert res.status_code == 400 and message in str(res.data["coupon"])
    assert ServiceRequest.objects.get(pk=req.pk).status == "open"  # rien n'est réservé


def test_code_limite_au_metier_et_aux_utilisations(world):
    other = Trade.objects.create(slug="menage", name="Ménage")
    c = coupon(max_uses_per_client=1)
    c.trades.add(other)
    with pytest.raises(Exception, match="ce métier"):
        booked(world, 20000, "CLIM20")
    c.trades.clear()
    first = booked(world, 20000, "CLIM20")
    with pytest.raises(Exception, match="déjà utilisé"):
        booked(world, 20000, "CLIM20")
    # Le client demande l'annulation après avoir réservé : en attendant le rappel du support,
    # le code reste consommé (pas de remise à répétition).
    services.cancel(world["client"], first, "solved")
    with pytest.raises(Exception, match="déjà utilisé"):
        booked(world, 20000, "CLIM20")
    # Seule une annulation par l'équipe le libère.
    c.max_uses_per_client = 2
    c.save()
    other_booking = booked(world, 20000, "CLIM20")
    services.staff_cancel(world["super"], other_booking, "Doublon")
    other_booking.refresh_from_db()
    assert (other_booking.coupon, other_booking.discount) == (None, 0)
    assert booked(world, 20000, "CLIM20").discount == 3000


def test_arrondi_au_franc_sans_float():
    assert services.percent_of(12345, 10) == 1235  # 1 234,5 → 1 235 (pas d'arrondi au pair)
    assert services.percent_of(20000, 12) == 2400


def test_seuls_le_pro_et_la_finance_voient_la_commission(world):
    req = booked(world)
    for user, visible in ((world["pro"], True), (world["finance"], True), (world["ops"], False)):
        money = as_user(user).get(f"/api/requests/{req.pk}/").data["money"]
        assert ("commission" in money) is visible


def test_montant_mal_saisi_refuse_sans_etre_recolle(world):
    api = as_user(world["marketing"])
    for value in ("7,5", "-3000"):
        res = api.post(
            "/api/console/coupons/", {"code": "ESSAI", "kind": "percent", "value": value}
        )
        assert res.status_code == 400, value
    assert not Coupon.objects.filter(code="ESSAI").exists()


def test_export_csv_neutralise_les_formules(world):
    req = booked(world)
    ServiceRequest.objects.filter(pk=req.pk).update(title='=HYPERLINK("http://x")')
    services.complete(world["client"], req)
    body = as_user(world["finance"]).get("/api/console/transactions/export/").content.decode()
    assert "'=HYPERLINK" in body


def test_premiere_commande_seulement(world):
    Coupon.objects.create(code="BIENVENUE", kind="fixed", value=2000, first_order_only=True)
    assert booked(world, 10000, "BIENVENUE").discount == 2000
    Coupon.objects.filter(code="BIENVENUE").update(max_uses_per_client=5)
    with pytest.raises(Exception, match="première mission"):
        booked(world, 10000, "BIENVENUE")


def test_creer_un_code_depuis_la_console(world):
    api = as_user(world["marketing"])
    res = api.post(
        "/api/console/coupons/",
        {
            "code": "tabaski",
            "kind": "fixed",
            "value": "3 000",
            "min_amount": "10000",
            "starts_on": "2026-06-01",
            "ends_on": "2026-06-10",
            "trades": ["climatisation"],
            "first_order_only": "0",
        },
        format="json",
    )
    assert res.status_code == 201, res.data
    assert (res.data["code"], res.data["value"], res.data["min_amount"]) == ("TABASKI", 3000, 10000)
    assert res.data["ends_on"] == "2026-06-10" and res.data["state"] == "expired"
    assert (
        api.post(
            "/api/console/coupons/", {"code": "TABASKI", "kind": "fixed", "value": "1"}
        ).status_code
        == 400
    )
    bad = api.post("/api/console/coupons/", {"code": "X1Y", "kind": "percent", "value": "150"})
    assert bad.status_code == 400
    assert as_user(world["finance"]).get("/api/console/coupons/").status_code == 403


# --- Campagnes ---------------------------------------------------------------------------------


def test_campagnes_publiques_en_cours(world):
    api = as_user(world["marketing"])
    res = api.post(
        "/api/console/campaigns/",
        {
            "title": "Clim",
            "message": "−20 %",
            "placement": "home",
            "cta_label": "Go",
            "cta_url": "/metiers",
        },
    )
    assert res.status_code == 201 and res.data["is_live"] is True
    Campaign.objects.create(title="Passée", message="…", ends_at=timezone.now() - timedelta(days=1))
    Campaign.objects.create(title="Formulaire", message="…", placement="request")
    public = APIClient().get("/api/campaigns/?placement=home").data
    assert [c["title"] for c in public] == ["Clim"]
    bad = api.post(
        "/api/console/campaigns/",
        {"title": "x", "message": "x", "placement": "home", "cta_url": "https://ailleurs.example"},
    )
    assert bad.status_code == 400  # lien externe refusé


def test_le_bandeau_annonce_les_conditions_du_code(world):
    c = coupon(min_amount=5000, first_order_only=True)
    end = timezone.make_aware(datetime(2030, 11, 12))  # fin exclusive : minuit du 12
    Campaign.objects.create(title="Clim", message="−20 %", coupon=c, ends_at=end)
    terms = APIClient().get("/api/campaigns/?placement=home").data[0]["terms"]
    assert terms == {
        "min_amount": 5000,
        "max_discount": 3000,
        "first_order_only": True,
        "ends_on": "2030-11-11",
    }


# --- Finances ----------------------------------------------------------------------------------


def test_transactions_et_soldes(world):
    coupon(max_discount=None)
    done = booked(world, 20000, "CLIM20")  # remise 4 000, commission 2 000 → Jeflink doit 2 000
    services.complete(world["client"], done)
    other = booked(world, 30000)  # commission 3 000
    services.complete(world["client"], other)
    booked(world, 50000)  # réservée, pas encore terminée : hors soldes

    api = as_user(world["finance"])
    res = api.get("/api/console/transactions/?status=done")
    assert res.data["count"] == 2
    assert res.data["totals"]["net"] == (2000 - 4000) + 3000
    csv = api.get("/api/console/transactions/export/")
    assert csv["Content-Type"].startswith("text/csv")
    assert "Net Jeflink" in csv.content.decode("utf-8-sig")

    balances = api.get("/api/console/balances/").data
    assert balances["results"][0]["balance"] == 1000  # le pro doit 1 000 F CFA
    pro_id = world["pro"].pk
    res = api.post(
        f"/api/console/balances/{pro_id}/settle/",
        {"direction": "to_jeflink", "amount": "1 000", "method": "wave", "reference": "W1"},
    )
    assert res.status_code == 200 and res.data["balance"] == 0
    assert res.data["settlements"][0]["method_label"] == "Wave"
    assert as_user(world["ops"]).get("/api/console/balances/").status_code == 403


def test_rapport_mensuel(world):
    req = booked(world, 20000)
    services.complete(world["client"], req)
    data = as_user(world["finance"]).get("/api/console/reports/").data
    assert data["months"][0]["count"] == 1 and data["months"][0]["commission"] == 2000
    assert data["by_trade"][0]["trade"] == "Froid et climatisation"
    assert as_user(world["finance"]).get("/api/console/reports/?month=abc").status_code == 400


# --- Annulation demandée par le client : droits, code promo, motif ------------------------------


def test_seule_l_equipe_operations_decide_apres_l_appel(world):
    req = booked(world)
    assert (
        as_user(world["pro"])
        .post(f"/api/requests/{req.pk}/cancel/", {"reason": "price"}, format="json")
        .status_code
        == 403
    )
    other = User.objects.create_user("autre@example.com", PASSWORD)
    assert (
        as_user(other)
        .post(f"/api/requests/{req.pk}/cancel/", {"reason": "price"}, format="json")
        .status_code
        == 404
    )
    services.cancel(world["client"], req, "price")
    for role in ("marketing", "finance"):
        for action in ("confirm-cancel", "keep"):
            res = as_user(world[role]).post(
                f"/api/console/requests/{req.pk}/{action}/", {"note": "Appelé."}, format="json"
            )
            assert res.status_code == 403
    too_long = {"note": "x" * 241}
    res = as_user(world["ops"]).post(
        f"/api/console/requests/{req.pk}/keep/", too_long, format="json"
    )
    assert res.status_code == 400


def test_motif_pro_seulement_si_un_pro_est_reserve(world):
    req = services.create_request(
        world["client"], trade=world["trade"], zone=world["zone"], title="Clim", description="…"
    )
    res = as_user(world["client"]).post(
        f"/api/requests/{req.pk}/cancel/", {"reason": "pro"}, format="json"
    )
    assert res.status_code == 400


def test_code_rendu_a_la_confirmation_seulement(world):
    coupon(max_uses_per_client=1)
    req = booked(world, 20000, "CLIM20")
    services.cancel(world["client"], req, "solved")
    req.refresh_from_db()
    assert req.coupon_id is not None  # en attente du rappel : le code reste consommé
    as_user(world["ops"]).post(
        f"/api/console/requests/{req.pk}/confirm-cancel/", {"note": "Réglé seul."}, format="json"
    )
    req.refresh_from_db()
    assert (req.status, req.coupon_id, req.discount) == ("cancelled", None, 0)
    assert booked(world, 20000, "CLIM20").discount > 0  # le client peut s'en resservir


def test_motif_efface_quand_la_mission_est_maintenue(world):
    req = booked(world)
    services.cancel(world["client"], req, "pro")
    as_user(world["ops"]).post(
        f"/api/console/requests/{req.pk}/keep/", {"note": "Malentendu."}, format="json"
    )
    services.staff_cancel(world["super"], req, "Client injoignable")
    seen = as_user(world["client"]).get(f"/api/requests/{req.pk}/").data
    assert seen["status"] == "cancelled" and seen["cancellation"] is None
    log = AuditLog.objects.filter(action="request.cancel_keep").get()
    assert log.details.startswith("Un souci avec le pro")


# --- Code promo côté client : saisi sur la demande, aperçu sur chaque devis -----------------


def test_code_saisi_a_la_publication(world):
    coupon()
    awa = as_user(world["client"])
    data = {"trade": "climatisation", "zone": "ouakam", "title": "Clim", "description": "…"}
    before = ServiceRequest.objects.count()
    res = awa.post("/api/requests/", {**data, "promo_code": "NIMPORTE"}, format="json")
    assert res.status_code == 400 and "promo_code" in res.data
    assert ServiceRequest.objects.count() == before  # rien de créé : le client corrige
    res = awa.post("/api/requests/", {**data, "promo_code": " clim20 "}, format="json")
    assert res.status_code == 201 and res.data["promo_code"] == "CLIM20"


def test_apercu_du_code_sur_chaque_devis_puis_application(world):
    coupon(min_amount=10000)
    client, pro = world["client"], world["pro"]
    req = services.create_request(
        client, trade=world["trade"], zone=world["zone"], title="Clim", description="…"
    )
    awa = as_user(client)
    assert (
        awa.post(f"/api/requests/{req.pk}/code/", {"code": "CLIM20"}, format="json").status_code
        == 200
    )
    services.submit_quote(pro, req, 20000)
    other = User.objects.create_user("pro2@example.com", PASSWORD, role=User.Role.PRO)
    ProProfile.objects.create(user=other, is_verified=True).trades.add(world["trade"])
    services.submit_quote(other, req, 8000)
    quotes = {
        q["amount"]: q["with_code"] for q in awa.get(f"/api/requests/{req.pk}/").data["quotes"]
    }
    assert quotes[20000] == {"code": "CLIM20", "discount": 3000, "client_pays": 17000}
    assert "au moins" in quotes[8000]["error"]
    # Le pro ne voit ni le code ni l'aperçu.
    seen = as_user(pro).get(f"/api/requests/{req.pk}/").data
    assert seen["promo_code"] == "" and all(q["with_code"] is None for q in seen["quotes"])
    # Le client choisit le devis sans ressaisir le code : il est appliqué.
    quote = req.quotes.get(amount=20000)
    res = awa.post(f"/api/requests/{req.pk}/accept/", {"quote_id": quote.pk}, format="json")
    assert res.status_code == 200 and res.data["money"]["discount"] == 3000


def test_code_refuse_ou_retire(world):
    coupon()
    req = services.create_request(
        world["client"], trade=world["trade"], zone=world["zone"], title="Clim", description="…"
    )
    awa = as_user(world["client"])
    url = f"/api/requests/{req.pk}/code/"
    assert awa.post(url, {"code": "INCONNU"}, format="json").data["code"]
    assert awa.post(url, {"code": "CLIM20"}, format="json").data["promo_code"] == "CLIM20"
    assert awa.post(url, {"code": ""}, format="json").data["promo_code"] == ""
    assert as_user(world["pro"]).post(url, {"code": "CLIM20"}, format="json").status_code == 403
