"""Console d'administration : accès réservé à l'équipe et chiffres du tableau de bord."""

import pytest
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from jeflink.accounts.models import ProProfile, User
from jeflink.catalog.models import Trade, Zone
from jeflink.jobs import services

pytestmark = pytest.mark.django_db


def as_user(user):
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Token {Token.objects.create(user=user).key}")
    return client


@pytest.fixture
def staff():
    return User.objects.create_user("equipe@jeflink.local", "x" * 12, is_staff=True)


@pytest.fixture
def mission():
    """Une demande réservée (12 500 F CFA) et un pro en attente de vérification."""
    trade = Trade.objects.create(slug="plomberie", name="Plomberie")
    zone = Zone.objects.create(slug="ouakam", name="Ouakam")
    client = User.objects.create_user("awa@example.com", "x" * 12)
    pro = User.objects.create_user("pro@example.com", "x" * 12, role=User.Role.PRO)
    profile = ProProfile.objects.create(user=pro, is_verified=True)
    profile.trades.add(trade)
    waiting = User.objects.create_user("nouveau@example.com", "x" * 12, role=User.Role.PRO)
    ProProfile.objects.create(user=waiting)
    req = services.create_request(client, trade=trade, zone=zone, title="Fuite", description="…")
    quote = services.submit_quote(pro, req, 12500)
    services.accept_quote(client, req, quote.pk)
    return req


ENDPOINTS = ["/api/console/overview/", "/api/console/badges/"]


@pytest.mark.parametrize("url", ENDPOINTS)
def test_console_refusee_hors_equipe(url):
    assert APIClient().get(url).status_code == 401
    client = User.objects.create_user("awa@example.com", "x" * 12)
    pro = User.objects.create_user("pro@example.com", "x" * 12, role=User.Role.PRO)
    assert as_user(client).get(url).status_code == 403
    assert as_user(pro).get(url).status_code == 403


def test_tableau_de_bord(staff, mission):
    res = as_user(staff).get("/api/console/overview/?days=7")
    assert res.status_code == 200
    data = res.data
    assert data["period_days"] == 7
    assert data["current"]["requests"] == 1
    assert data["current"]["booking_rate"] == 100
    assert data["current"]["volume"] == 12500  # entier F CFA
    assert data["counts"]["pros_pending"] == 1
    waiting = User.objects.get(email="nouveau@example.com")
    assert data["alerts"]["pending_pros"][0]["id"] == waiting.pk
    assert len(data["daily"]) == 7
    assert sum(d["booked"] for d in data["daily"]) == 1
    assert data["top_pros"][0]["volume"] == 12500
    assert [e["status"] for e in data["activity"]] == ["booked", "open"]


def test_pastilles_du_menu(staff, mission):
    res = as_user(staff).get("/api/console/badges/")
    assert res.data == {
        "pros_pending": 1,
        "stale_requests": 0,
        "contact_unhandled": 0,
        "disputes_active": 0,
    }


def test_periode_inconnue_revient_a_30_jours(staff):
    assert as_user(staff).get("/api/console/overview/?days=3").data["period_days"] == 30
