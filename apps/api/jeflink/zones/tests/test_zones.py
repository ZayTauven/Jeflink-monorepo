import pytest
from django.contrib.gis.geos import MultiPolygon, Point, Polygon
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from jeflink.catalog.tests.factories import TradeFactory
from jeflink.zones.models import Zone
from jeflink.zones.selectors import (
    availability,
    resolve_zone_text,
    unknown_zone_text,
    zones_for_point,
)
from jeflink.zones.services import open_trade_in_all_zones, save_zone

from .factories import CityFactory, ZoneFactory

pytestmark = pytest.mark.django_db

PIKINE = Point(-17.3900, 14.7550, srid=4326)
GUEDIAWAYE = Point(-17.3950, 14.7760, srid=4326)


def square(lon, lat, half=0.005):
    return MultiPolygon(
        Polygon.from_bbox((lon - half, lat - half, lon + half, lat + half)), srid=4326
    )


# --- Modèle et services ------------------------------------------------------------------


def test_rayon_borne_en_base():
    for radius in (199, 15_001):
        with pytest.raises(IntegrityError), transaction.atomic():
            ZoneFactory(radius_m=radius)


def test_save_zone_slug_fige():
    zone = ZoneFactory(slug="pikine")
    zone.slug = "pikine-ville"
    with pytest.raises(ValidationError):
        save_zone(zone=zone)


def test_open_trade_in_all_zones_seulement_les_zones_actives():
    trade = TradeFactory()
    deja = ZoneFactory(trades=[trade])
    a_ouvrir = ZoneFactory()
    inactive = ZoneFactory(is_active=False)
    assert open_trade_in_all_zones(trade=trade) == 1
    assert set(trade.zones.all()) == {deja, a_ouvrir}
    assert inactive not in trade.zones.all()


# --- zones_for_point ---------------------------------------------------------------------


def test_point_dans_un_cercle():
    pikine = ZoneFactory(slug="pikine", center=PIKINE, radius_m=4000)
    assert zones_for_point(Point(-17.3920, 14.7600, srid=4326)) == [pikine]


def test_deux_cercles_qui_se_chevauchent_deux_candidates_triees():
    pikine = ZoneFactory(slug="pikine", center=PIKINE, radius_m=4000)
    guediawaye = ZoneFactory(slug="guediawaye", center=GUEDIAWAYE, radius_m=3500)
    plus_pres_de_pikine = Point(-17.3910, 14.7600, srid=4326)
    assert zones_for_point(plus_pres_de_pikine) == [pikine, guediawaye]
    plus_pres_de_guediawaye = Point(-17.3940, 14.7720, srid=4326)
    assert zones_for_point(plus_pres_de_guediawaye) == [guediawaye, pikine]


def test_le_contour_prime_sur_le_cercle():
    point = Point(-17.4000, 14.7000, srid=4326)
    # Centre lointain, rayon court : seul le contour contient le point.
    par_contour = ZoneFactory(
        center=Point(-17.45, 14.75, srid=4326), radius_m=200, boundary=square(-17.4000, 14.7000)
    )
    # Cercle qui contient le point, mais contour saisi ailleurs : écartée.
    ZoneFactory(center=point, radius_m=3000, boundary=square(-17.30, 14.80))
    assert zones_for_point(point) == [par_contour]


def test_point_hors_zone_et_zone_inactive():
    ZoneFactory(center=PIKINE, radius_m=4000, is_active=False)
    ZoneFactory(city=CityFactory(slug="thies", name="Thiès", is_active=False), center=PIKINE)
    assert zones_for_point(PIKINE) == []
    ZoneFactory(center=PIKINE, radius_m=4000)
    assert zones_for_point(Point(-17.0, 14.5, srid=4326)) == []


# --- resolve_zone_text -------------------------------------------------------------------


@pytest.fixture
def quartiers():
    return {
        "parcelles": ZoneFactory(
            slug="parcelles-assainies",
            name="Parcelles Assainies",
            aliases=["Parcelles", "PA", "Unité 15"],
            position=1,
        ),
        "patte": ZoneFactory(slug="patte-doie", name="Patte d'Oie", aliases=["Pattedoie"]),
        "sacre": ZoneFactory(slug="sacre-coeur", name="Sacré-Cœur", aliases=["Sacré-Cœur 1"]),
        "liberte": ZoneFactory(slug="liberte", name="Liberté", aliases=["Sicap", "Sicap Baobab"]),
    }


@pytest.mark.parametrize(
    ("texte", "attendu"),
    [
        ("PA", "parcelles"),
        ("parcelle", "parcelles"),
        ("Sacre Coeur", "sacre"),
        ("Sicap", "liberte"),
        ("baobab", "liberte"),
        ("patte d'oie", "patte"),
    ],
)
def test_resolve_zone_text(quartiers, texte, attendu):
    assert resolve_zone_text(texte) == [quartiers[attendu]]


def test_resolve_zone_text_inconnu(quartiers):
    assert resolve_zone_text("Gorée") == []
    assert resolve_zone_text("pa") == [quartiers["parcelles"]]


def test_unknown_zone_text_sans_chiffres_et_borne():
    assert unknown_zone_text("Cité Keur Gorgui, villa 12") == "cite keur gorgui villa"
    assert len(unknown_zone_text("x" * 100)) == 40


# --- availability ------------------------------------------------------------------------


@pytest.fixture
def plomberie():
    return TradeFactory(slug="plombier")


def test_disponible(plomberie):
    zone = ZoneFactory(slug="ouakam", trades=[plomberie])
    result = availability(trade_slug="plombier", zone_slug="ouakam")
    assert result.available and result.zone == zone


@pytest.mark.parametrize(
    ("setup", "kwargs", "status"),
    [
        (lambda t: None, {"trade_slug": "vitrier", "zone_slug": "ouakam"}, "trade_not_found"),
        (
            lambda t: Zone.objects.none(),
            {"trade_slug": "plombier", "zone_slug": "inconnue"},
            "zone_not_found",
        ),
        (
            lambda t: ZoneFactory(slug="ouakam", is_active=False, trades=[t]),
            {"trade_slug": "plombier", "zone_slug": "ouakam"},
            "zone_inactive",
        ),
        (
            lambda t: ZoneFactory(slug="ouakam"),
            {"trade_slug": "plombier", "zone_slug": "ouakam"},
            "trade_not_in_zone",
        ),
    ],
)
def test_motifs(plomberie, setup, kwargs, status):
    setup(plomberie)
    assert availability(**kwargs).status == status


def test_metier_inactif(plomberie):
    plomberie.is_active = False
    plomberie.save()
    ZoneFactory(slug="ouakam", trades=[plomberie])
    assert availability(trade_slug="plombier", zone_slug="ouakam").status == "trade_inactive"


def test_ville_inactive(plomberie):
    ZoneFactory(slug="ouakam", city=CityFactory(slug="dakar", is_active=False), trades=[plomberie])
    CityFactory._meta.model.objects.filter(slug="dakar").update(is_active=False)
    assert availability(trade_slug="plombier", zone_slug="ouakam").status == "zone_inactive"


def test_texte_libre(plomberie):
    zone = ZoneFactory(
        slug="parcelles-assainies", name="Parcelles Assainies", aliases=["PA"], trades=[plomberie]
    )
    assert availability(trade_slug="plombier", zone_text="PA").zone == zone
    unknown = availability(trade_slug="plombier", zone_text="Gorée, quai 3")
    assert (unknown.status, unknown.zone_text) == ("zone_unknown", "goree quai")


def test_point(plomberie):
    pikine = ZoneFactory(slug="pikine", center=PIKINE, radius_m=4000, trades=[plomberie])
    ZoneFactory(slug="guediawaye", center=GUEDIAWAYE, radius_m=3500, trades=[plomberie])
    assert (
        availability(trade_slug="plombier", point=Point(-17.3800, 14.7450, srid=4326)).zone
        == pikine
    )
    ambigu = availability(trade_slug="plombier", point=Point(-17.3910, 14.7600, srid=4326))
    assert ambigu.status == "zone_ambiguous"
    assert [z.slug for z in ambigu.candidates] == ["pikine", "guediawaye"]
    loin = availability(trade_slug="plombier", point=Point(-17.0, 14.5, srid=4326))
    assert loin.status == "out_of_area"
    assert loin.nearest_zone_slug in {"pikine", "guediawaye"}
    assert isinstance(loin.distance_km, int) and loin.distance_km > 30


def test_un_seul_lieu_exige(plomberie):
    with pytest.raises(ValueError):
        availability(trade_slug="plombier")
    with pytest.raises(ValueError):
        availability(trade_slug="plombier", zone_slug="a", zone_text="b")
