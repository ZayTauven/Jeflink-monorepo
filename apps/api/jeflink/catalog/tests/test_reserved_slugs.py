"""Slugs réservés partagés avec le web (spec 006, ADR 0013) : un seul fichier JSON."""

import json

import pytest
from django.core.exceptions import ValidationError

from jeflink.catalog.checks import reserved_trade_slugs
from jeflink.catalog.models import (
    RESERVED_SLUGS_FILE,
    RESERVED_TRADE_SLUGS,
    RESERVED_ZONE_SLUGS,
    Trade,
)
from jeflink.catalog.services import save_trade
from jeflink.zones.checks import reserved_zone_slugs
from jeflink.zones.models import Zone
from jeflink.zones.services import save_zone
from jeflink.zones.tests.factories import CityFactory, ZoneFactory

from .factories import TradeFactory

pytestmark = pytest.mark.django_db

AJOUTS_SPEC = {
    "fr", "wo", "en", "og", "opengraph-image", "twitter-image", "icon", "apple-icon", "manifest",
    "sitemap", "robots", "garantie", "tarifs", "comment-ca-marche", "services", "merci",
    "hors-ligne", "recherche",
}  # fmt: skip


def test_le_fichier_json_alimente_django():
    data = json.loads(RESERVED_SLUGS_FILE.read_text(encoding="utf-8"))
    assert frozenset(data["trade_slugs"]) == RESERVED_TRADE_SLUGS
    assert frozenset(data["zone_slugs"]) == RESERVED_ZONE_SLUGS
    assert len(data["trade_slugs"]) == len(set(data["trade_slugs"]))  # pas de doublon


def test_les_ajouts_de_la_spec_sont_reserves():
    assert AJOUTS_SPEC <= RESERVED_TRADE_SLUGS
    assert {"opengraph-image", "twitter-image"} == RESERVED_ZONE_SLUGS


def test_les_slugs_reserves_sont_bien_formes():
    # Un slug réservé qui ne passerait pas le motif serait un ajout inutile.
    from jeflink.common.slugs import validate_reference_slug

    for slug in RESERVED_TRADE_SLUGS | RESERVED_ZONE_SLUGS:
        validate_reference_slug(slug)


@pytest.mark.parametrize("slug", sorted(AJOUTS_SPEC))
def test_metier_a_slug_reserve_refuse(slug):
    with pytest.raises(ValidationError) as exc:
        save_trade(trade=Trade(slug=slug, name_fr="X"))
    assert exc.value.error_dict["slug"][0].code == "slug_reserved"


@pytest.mark.parametrize("slug", ["opengraph-image", "twitter-image"])
def test_zone_a_slug_reserve_refusee(slug):
    from django.contrib.gis.geos import Point

    with pytest.raises(ValidationError) as exc:
        save_zone(zone=Zone(city=CityFactory(), slug=slug, name="X", center=Point(-17.4, 14.7)))
    assert exc.value.error_dict["slug"][0].code == "slug_reserved"


def test_un_slug_de_metier_reserve_reste_permis_pour_une_zone():
    # « recherche » est réservé au premier segment seulement.
    zone = ZoneFactory(slug="recherche")
    zone.full_clean()


def test_controle_au_demarrage_sans_conflit():
    TradeFactory(slug="plombier")
    ZoneFactory(slug="ouakam")
    assert reserved_trade_slugs(None, databases={"default"}) == []
    assert reserved_zone_slugs(None, databases={"default"}) == []


def test_controle_au_demarrage_trouve_un_slug_reserve_deja_en_base():
    TradeFactory(slug="tarifs")  # la factory ne valide pas : saisie antérieure à la règle
    ZoneFactory(slug="opengraph-image")
    trades = reserved_trade_slugs(None, databases={"default"})
    zones = reserved_zone_slugs(None, databases={"default"})
    assert [e.id for e in trades] == ["catalog.E001"]
    assert [e.id for e in zones] == ["zones.E001"]
    assert "tarifs" in trades[0].msg


def test_controle_ignore_une_base_non_ciblee():
    TradeFactory(slug="tarifs")
    assert reserved_trade_slugs(None, databases=None) == []
