"""Saisie Ops dans l'admin Django (spec 002) : modifier oui, supprimer ou changer un slug non."""

import pytest
from django.contrib.auth.models import Group
from django.urls import reverse

from jeflink.accounts.models import User
from jeflink.catalog.models import Trade
from jeflink.zones.tests.factories import ZoneFactory

from .factories import ServiceFactory, TradeFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _second_facteur_valide(monkeypatch):
    # Le second facteur de l'admin est testé par accounts (tâche 21) ; ici, on teste la saisie.
    monkeypatch.setattr("jeflink.accounts.admin_site.admin_mfa_valid", lambda request: True)


@pytest.fixture
def saisie(client):
    """Compte technique du groupe « Saisie catalogue », sans être superutilisateur."""
    user = User.objects.create_user("+221770000501", is_staff=True)
    user.groups.add(Group.objects.get(name="Saisie catalogue"))
    client.force_login(user)
    return client


def trade_form(**overrides):
    data = {
        "slug": "vitrier",
        "name_fr": "Vitrerie",
        "name_wo": "",
        "short_description_fr": "",
        "short_description_wo": "",
        "seo_title_fr": "",
        "seo_title_wo": "",
        "aliases": "vitre, verre",
        "icon_key": "",
        "is_active": "on",
        "position": "100",
        "services-TOTAL_FORMS": "0",
        "services-INITIAL_FORMS": "0",
        "services-MIN_NUM_FORMS": "0",
        "services-MAX_NUM_FORMS": "1000",
    }
    data.update(overrides)
    return data


def test_le_groupe_cree_un_metier(saisie):
    response = saisie.post(reverse("admin:catalog_trade_add"), trade_form())
    assert response.status_code == 302
    assert Trade.objects.get(slug="vitrier").aliases == ["vitre", "verre"]


@pytest.mark.parametrize("slug", ["connexion", "Vitrier"])
def test_slug_reserve_ou_mal_forme_refuse(saisie, slug):
    response = saisie.post(reverse("admin:catalog_trade_add"), trade_form(slug=slug))
    assert response.status_code == 200  # formulaire réaffiché avec l'erreur
    assert not Trade.objects.filter(slug=slug).exists()


def test_slug_fige_a_la_modification(saisie):
    trade = TradeFactory(slug="vitrier")
    service = ServiceFactory(trade=trade, slug="pose")
    data = trade_form(
        slug="vitrerie",
        name_fr="Vitrerie et miroirs",
        **{
            "services-TOTAL_FORMS": "1",
            "services-INITIAL_FORMS": "1",
            "services-0-id": str(service.pk),
            "services-0-trade": str(trade.pk),
            "services-0-slug": "pose-de-vitre",
            "services-0-name_fr": "Pose de vitre",
            "services-0-position": "1",
            "services-0-is_active": "on",
        },
    )
    response = saisie.post(reverse("admin:catalog_trade_change", args=[trade.pk]), data)
    assert response.status_code == 302
    trade.refresh_from_db()
    service.refresh_from_db()
    assert (trade.slug, trade.name_fr) == ("vitrier", "Vitrerie et miroirs")
    assert (service.slug, service.name_fr) == ("pose", "Pose de vitre")


def test_aucune_suppression(saisie):
    trade = TradeFactory()
    zone = ZoneFactory()
    assert saisie.get(reverse("admin:catalog_trade_delete", args=[trade.pk])).status_code == 403
    assert saisie.get(reverse("admin:zones_zone_delete", args=[zone.pk])).status_code == 403
    assert Trade.objects.filter(pk=trade.pk).exists()


def test_action_ouvrir_partout(saisie):
    trade = TradeFactory()
    zones = [ZoneFactory(), ZoneFactory()]
    response = saisie.post(
        reverse("admin:catalog_trade_changelist"),
        {"action": "open_everywhere", "_selected_action": [trade.pk]},
    )
    assert response.status_code == 302
    assert set(trade.zones.all()) == set(zones)


def test_carte_et_cases_des_zones(saisie):
    TradeFactory(name_fr="Plomberie")
    response = saisie.get(reverse("admin:zones_zone_add"))
    assert response.status_code == 200
    assert b'type="checkbox" name="trades"' in response.content


def test_le_reste_de_l_admin_reste_en_lecture_seule(saisie):
    assert saisie.get(reverse("admin:accounts_user_changelist")).status_code == 403
