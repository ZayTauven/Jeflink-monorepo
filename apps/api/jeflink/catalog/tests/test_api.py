"""Endpoints publics du catalogue et des zones (spec 002)."""

import pytest
from django.urls import reverse

from jeflink.catalog.api.views import TradeDetailView, TradeListView
from jeflink.zones.api.views import ZoneListView, ZoneTradesView
from jeflink.zones.tests.factories import CityFactory, ZoneFactory

from .factories import ServiceFactory, TradeFactory

pytestmark = pytest.mark.django_db

PUBLIC = "public, max-age=300, stale-while-revalidate=86400"


@pytest.fixture
def referentiel():
    plomberie = TradeFactory(slug="plombier", name_fr="Plomberie", aliases=["fuite"], position=1)
    menage = TradeFactory(
        slug="menage", name_fr="Ménage", seo_title_fr="Femme de ménage et nettoyage", position=2
    )
    TradeFactory(slug="ferme", is_active=False)
    ServiceFactory(trade=plomberie, slug="fuite", name_fr="Fuite", urgent=True, position=1)
    ServiceFactory(
        trade=plomberie, slug="chauffe-eau", name_fr="Chauffe-eau", price_from_xof=15000, position=2
    )
    ServiceFactory(trade=plomberie, slug="retire", is_active=False)
    ouakam = ZoneFactory(slug="ouakam", name="Ouakam", position=4, trades=[plomberie, menage])
    ZoneFactory(slug="pikine", name="Pikine", position=2, trades=[menage])
    ZoneFactory(slug="ngor", name="Ngor", is_active=False, trades=[plomberie])
    return {"plomberie": plomberie, "ouakam": ouakam}


@pytest.mark.parametrize("view", [TradeListView, TradeDetailView, ZoneListView, ZoneTradesView])
def test_vues_publiques_limitees_et_sans_authentification(view, settings):
    assert view.rate_limit_scope == "catalog_read" in settings.IP_RATE_LIMITS
    assert view.authentication_classes == []


def test_liste_des_metiers(api_client, referentiel):
    response = api_client.get(reverse("catalog-trades"))
    assert response.status_code == 200
    assert response["Cache-Control"] == PUBLIC
    assert response["ETag"]
    assert [t["slug"] for t in response.json()] == ["plombier", "menage"]
    plomberie = response.json()[0]
    assert plomberie == {
        "slug": "plombier",
        "name": {"fr": "Plomberie", "wo": None},
        "short_description": None,
        "icon_key": None,
        "aliases": ["fuite"],
    }


def test_detail_d_un_metier(api_client, referentiel):
    data = api_client.get(reverse("catalog-trade", args=["plombier"])).json()
    assert [s["slug"] for s in data["services"]] == ["fuite", "chauffe-eau"]
    assert data["services"][0] == {
        "slug": "fuite",
        "name": {"fr": "Fuite", "wo": None},
        "aliases": [],
        "price_from_xof": None,
        "urgent": True,
    }
    assert data["services"][1]["price_from_xof"] == 15000
    assert data["zones"] == ["ouakam"]  # Ngor est inactive
    assert data["seo_title"] == {"fr": "Plomberie", "wo": None}
    menage = api_client.get(reverse("catalog-trade", args=["menage"])).json()
    assert menage["seo_title"]["fr"] == "Femme de ménage et nettoyage"
    assert menage["zones"] == ["pikine", "ouakam"]


@pytest.mark.parametrize("slug", ["ferme", "inconnu"])
def test_metier_inactif_ou_inconnu(api_client, referentiel, slug):
    response = api_client.get(reverse("catalog-trade", args=[slug]))
    assert (response.status_code, response.json()) == (404, {"code": "trade_not_found"})


def test_liste_des_zones(api_client, referentiel):
    CityFactory(slug="thies", name="Thiès")
    ZoneFactory(slug="mbour", city=CityFactory(slug="mbour", name="Mbour", is_active=False))
    data = api_client.get(reverse("zones")).json()
    assert [z["slug"] for z in data] == ["pikine", "ouakam"]
    assert data[0] == {"slug": "pikine", "name": "Pikine", "city": "dakar", "aliases": []}
    assert api_client.get(reverse("zones"), {"city": "thies"}).json() == []


def test_metiers_d_une_zone(api_client, referentiel):
    data = api_client.get(reverse("zone-trades", args=["pikine"])).json()
    assert [t["slug"] for t in data] == ["menage"]
    for slug in ("ngor", "inconnue"):
        response = api_client.get(reverse("zone-trades", args=[slug]))
        assert (response.status_code, response.json()) == (404, {"code": "zone_not_found"})


def test_etag_et_304(api_client, referentiel):
    url = reverse("catalog-trades")
    etag = api_client.get(url)["ETag"]
    not_modified = api_client.get(url, HTTP_IF_NONE_MATCH=etag)
    assert not_modified.status_code == 304
    assert not_modified["ETag"] == etag
    assert not not_modified.content
    assert api_client.get(url, HTTP_IF_NONE_MATCH=f'W/{etag}, "autre"').status_code == 304
    referentiel["plomberie"].name_fr = "Plomberie générale"
    referentiel["plomberie"].save()
    assert api_client.get(url, HTTP_IF_NONE_MATCH=etag).status_code == 200


def test_avec_jeton_jamais_en_cache_public(api_client, referentiel):
    response = api_client.get(reverse("catalog-trades"), HTTP_AUTHORIZATION="Bearer faux")
    # Le jeton n'est pas lu (vue publique), mais la réponse ne doit jamais être partagée.
    assert response.status_code == 200
    assert response["Cache-Control"] == "private, no-store"


@pytest.mark.parametrize("method", ["post", "put", "patch", "delete"])
def test_ecriture_refusee(api_client, referentiel, method):
    response = getattr(api_client, method)(reverse("catalog-trades"))
    assert response.status_code == 405


def test_liste_bornee(api_client, settings):
    settings.REFERENCE_LIST_MAX = 3
    for _ in range(5):
        TradeFactory()
    assert len(api_client.get(reverse("catalog-trades")).json()) == 3


def test_wo_renseigne(api_client):
    TradeFactory(slug="plombier", name_fr="Plomberie", name_wo="Plombie")
    assert api_client.get(reverse("catalog-trades")).json()[0]["name"] == {
        "fr": "Plomberie",
        "wo": "Plombie",
    }
