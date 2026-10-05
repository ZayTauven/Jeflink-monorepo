"""Détail d'une zone et couverture du catalogue pour le site public (spec 006)."""

from datetime import timedelta

import pytest
from django.contrib.gis.geos import Point
from django.urls import reverse
from django.utils import timezone

from jeflink.catalog.models import Service, Trade
from jeflink.catalog.tests.factories import ServiceFactory, TradeFactory
from jeflink.zones.api.views import ZoneDetailView
from jeflink.zones.models import Zone
from jeflink.zones.selectors import coverage, is_indexable, nearby_zones

from .factories import CityFactory, ZoneFactory

pytestmark = pytest.mark.django_db

PUBLIC = "public, max-age=300, stale-while-revalidate=86400"


def at(lon: float, lat: float) -> Point:
    return Point(lon, lat, srid=4326)


@pytest.fixture
def dakar():
    plomberie = TradeFactory(slug="plombier", name_fr="Plomberie", position=1)
    menage = TradeFactory(slug="menage", name_fr="Ménage", position=2)
    ouakam = ZoneFactory(
        slug="ouakam",
        name="Ouakam",
        center=at(-17.4900, 14.7200),
        locative_fr="à Ouakam",
        seo_intro_fr="Ouakam, derrière la mosquée, près de la route de l'aéroport.",
        trades=[plomberie, menage],
    )
    # Du plus proche au plus loin d'Ouakam : Almadies, Ngor, Yoff, Pikine.
    ngor = ZoneFactory(slug="ngor", name="Ngor", center=at(-17.5100, 14.7500), trades=[menage])
    yoff = ZoneFactory(slug="yoff", name="Yoff", center=at(-17.4900, 14.7600), trades=[plomberie])
    almadies = ZoneFactory(
        slug="almadies",
        name="Almadies",
        center=at(-17.5000, 14.7400),
        locative_fr="aux Almadies",
        trades=[plomberie],
    )
    pikine = ZoneFactory(
        slug="pikine", name="Pikine", center=at(-17.3900, 14.7550), trades=[plomberie]
    )
    return {
        "plomberie": plomberie,
        "menage": menage,
        "ouakam": ouakam,
        "ngor": ngor,
        "yoff": yoff,
        "almadies": almadies,
        "pikine": pikine,
    }


def get_zone(client, slug, **params):
    return client.get(reverse("zone", args=[slug]), params)


def coverage_pairs(client):
    return {(p["trade"], p["zone"]) for p in client.get(reverse("catalog-coverage")).json()}


# --- Sélecteurs ---------------------------------------------------------------------------


def test_nearby_zones_tri_par_distance_et_limite(dakar):
    assert [z.slug for z in nearby_zones(dakar["ouakam"])] == [
        "almadies",
        "ngor",
        "yoff",
        "pikine",
    ]
    assert [z.slug for z in nearby_zones(dakar["ouakam"], limit=2)] == ["almadies", "ngor"]


def test_nearby_zones_exclut_la_zone_les_inactives_et_les_villes_inactives(dakar):
    ZoneFactory(slug="inactive", center=at(-17.4901, 14.7201), is_active=False)
    ville = CityFactory(slug="thies", name="Thiès", is_active=False)
    ZoneFactory(slug="thies-ville", city=ville, center=at(-17.4902, 14.7202))
    slugs = [z.slug for z in nearby_zones(dakar["ouakam"])]
    assert "ouakam" not in slugs
    assert "inactive" not in slugs
    assert "thies-ville" not in slugs


def test_nearby_zones_limitees_au_metier(dakar):
    assert [z.slug for z in nearby_zones(dakar["ouakam"], trade=dakar["menage"])] == ["ngor"]
    slugs = [z.slug for z in nearby_zones(dakar["ouakam"], trade=dakar["plomberie"])]
    assert slugs == ["almadies", "yoff", "pikine"]


def test_is_indexable_depend_du_texte_fr_seulement(dakar):
    assert is_indexable(dakar["ouakam"])
    ngor = dakar["ngor"]
    assert not is_indexable(ngor)
    ngor.seo_intro_wo = "Mbind"
    assert not is_indexable(ngor)  # le wolof seul ne rend pas la page indexable
    ngor.seo_intro_fr = "   "
    assert not is_indexable(ngor)


# --- GET /api/zones/{slug}/ ---------------------------------------------------------------


def test_vue_publique_limitee_et_sans_authentification(settings):
    assert ZoneDetailView.rate_limit_scope == "catalog_read" in settings.IP_RATE_LIMITS
    assert ZoneDetailView.authentication_classes == []


def test_detail_d_une_zone(api_client, dakar):
    response = get_zone(api_client, "ouakam")
    assert response.status_code == 200
    assert response["Cache-Control"] == PUBLIC
    assert response["ETag"]
    data = response.json()
    assert data["slug"] == "ouakam"
    assert data["name"] == "Ouakam"
    assert data["city"] == "dakar"
    assert data["locative"] == {"fr": "à Ouakam", "wo": None}
    assert data["intro"]["fr"].startswith("Ouakam, derrière")
    assert data["indexable"] is True
    assert [z["slug"] for z in data["nearby"]] == ["almadies", "ngor", "yoff", "pikine"]
    assert data["nearby"][0] == {"slug": "almadies", "name": "Almadies"}


def test_detail_sans_textes_saisis(api_client, dakar):
    data = get_zone(api_client, "ngor").json()
    assert data["locative"] is None
    assert data["intro"] is None
    assert data["indexable"] is False


def test_detail_n_expose_ni_position_ni_rayon_ni_distance(api_client, dakar):
    data = get_zone(api_client, "ouakam", trade="plombier").json()
    assert set(data) == {
        "slug",
        "name",
        "city",
        "aliases",
        "locative",
        "intro",
        "indexable",
        "nearby",
    }
    for neighbour in data["nearby"]:
        assert set(neighbour) == {"slug", "name"}
    body = get_zone(api_client, "ouakam").content.decode()
    for forbidden in ("center", "radius", "boundary", "distance", "lat", "lon", "-17.49"):
        assert forbidden not in body


def test_detail_voisins_limites_au_metier(api_client, dakar):
    data = get_zone(api_client, "ouakam", trade="menage").json()
    assert [z["slug"] for z in data["nearby"]] == ["ngor"]


def test_detail_metier_inconnu_ou_inactif(api_client, dakar):
    TradeFactory(slug="ferme", is_active=False)
    for slug in ("inconnu", "ferme"):
        response = get_zone(api_client, "ouakam", trade=slug)
        assert (response.status_code, response.json()) == (404, {"code": "trade_not_found"})


@pytest.mark.parametrize("slug", ["inconnue", "inactive", "ville-inactive"])
def test_detail_zone_inactive_ou_inconnue(api_client, dakar, slug):
    ZoneFactory(slug="inactive", is_active=False)
    ZoneFactory(slug="ville-inactive", city=CityFactory(slug="thies", is_active=False))
    response = get_zone(api_client, slug)
    assert (response.status_code, response.json()) == (404, {"code": "zone_not_found"})


def test_detail_304_avec_etag(api_client, dakar):
    url = reverse("zone", args=["ouakam"])
    first = api_client.get(url)
    second = api_client.get(url, headers={"If-None-Match": first["ETag"]})
    assert second.status_code == 304
    assert second["ETag"] == first["ETag"]
    assert second["Cache-Control"] == PUBLIC
    Zone.objects.filter(pk=dakar["ouakam"].pk).update(seo_intro_fr="Autre texte.")
    third = api_client.get(url, headers={"If-None-Match": first["ETag"]})
    assert third.status_code == 200


def test_detail_refuse_les_ecritures(api_client, dakar):
    assert api_client.post(reverse("zone", args=["ouakam"]), {}).status_code == 405


def test_la_route_trades_reste_servie(api_client, dakar):
    assert api_client.get(reverse("zone-trades", args=["ouakam"])).status_code == 200


# --- GET /api/catalog/coverage/ -----------------------------------------------------------


def test_couverture_des_paires_ouvertes(api_client, dakar):
    response = api_client.get(reverse("catalog-coverage"))
    assert response.status_code == 200
    assert response["Cache-Control"] == PUBLIC
    assert response["ETag"]
    pairs = {(p["trade"], p["zone"]): p for p in response.json()}
    assert set(pairs) == {
        ("plombier", "ouakam"),
        ("plombier", "yoff"),
        ("plombier", "almadies"),
        ("plombier", "pikine"),
        ("menage", "ouakam"),
        ("menage", "ngor"),
    }
    assert pairs[("plombier", "ouakam")]["indexable"] is True
    assert pairs[("plombier", "yoff")]["indexable"] is False
    assert set(pairs[("menage", "ngor")]) == {"trade", "zone", "indexable", "updated_at"}


def test_couverture_ordre_par_metier_puis_popularite_de_la_zone(dakar):
    trades = [p.trade for p in coverage()]
    assert trades == ["plombier"] * 4 + ["menage"] * 2


def test_couverture_exclut_fermees_et_inactifs(api_client, dakar):
    ancien = TradeFactory(slug="ancien", is_active=False)
    ZoneFactory(slug="zone-fermee", is_active=False, trades=[dakar["plomberie"], ancien])
    ville = CityFactory(slug="thies", name="Thiès", is_active=False)
    ZoneFactory(slug="thies-ville", city=ville, trades=[dakar["plomberie"]])
    ZoneFactory(slug="sans-metier")
    ZoneFactory(slug="ouverte-ancien", trades=[ancien])  # le métier est inactif
    pairs = coverage_pairs(api_client)
    assert {zone for _, zone in pairs}.isdisjoint(
        {"zone-fermee", "thies-ville", "sans-metier", "ouverte-ancien"}
    )
    assert "ancien" not in {trade for trade, _ in pairs}


def test_couverture_suit_l_ouverture_et_la_fermeture_d_un_metier(api_client, dakar):
    dakar["ouakam"].trades.remove(dakar["menage"])
    assert ("menage", "ouakam") not in coverage_pairs(api_client)
    dakar["ouakam"].trades.add(dakar["menage"])
    assert ("menage", "ouakam") in coverage_pairs(api_client)


def test_couverture_updated_at_le_plus_recent_du_metier_des_services_et_de_la_zone(dakar):
    base = timezone.now() - timedelta(days=30)
    Trade.objects.filter(pk=dakar["menage"].pk).update(updated_at=base)
    Zone.objects.filter(pk=dakar["ngor"].pk).update(updated_at=base + timedelta(days=1))

    def stamp():
        return next(p.updated_at for p in coverage() if (p.trade, p.zone) == ("menage", "ngor"))

    assert stamp() == base + timedelta(days=1)  # la zone, sans services
    service = ServiceFactory(trade=dakar["menage"], slug="repassage")
    assert stamp() == service.updated_at  # un service plus récent
    Service.objects.filter(pk=service.pk).update(
        updated_at=base - timedelta(days=5), is_active=False
    )
    assert stamp() == base + timedelta(days=1)  # un service retiré ne ramène pas plus tard
    Trade.objects.filter(pk=dakar["menage"].pk).update(updated_at=base + timedelta(days=2))
    assert stamp() == base + timedelta(days=2)  # le métier


def test_couverture_bornee(api_client, dakar, settings):
    settings.COVERAGE_LIST_MAX = 2
    assert len(api_client.get(reverse("catalog-coverage")).json()) == 2
    settings.COVERAGE_LIST_MAX = 5_000
    assert len(api_client.get(reverse("catalog-coverage")).json()) == 6


def test_la_borne_par_defaut_est_de_5000(settings):
    assert settings.COVERAGE_LIST_MAX == 5_000


def test_couverture_304(api_client, dakar):
    url = reverse("catalog-coverage")
    first = api_client.get(url)
    assert api_client.get(url, headers={"If-None-Match": first["ETag"]}).status_code == 304


def test_couverture_refuse_les_ecritures(api_client, dakar):
    assert api_client.post(reverse("catalog-coverage"), {}).status_code == 405


def test_couverture_en_deux_requetes_au_plus(dakar, django_assert_max_num_queries):
    with django_assert_max_num_queries(2):
        coverage()
