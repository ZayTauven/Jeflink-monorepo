"""Textes publiés tels quels (spec 006) : ni numéro, ni lien, ni domaine, ni pseudo."""

import pytest
from django.core.exceptions import ValidationError

from jeflink.catalog.models import Service, Trade
from jeflink.catalog.services import save_service, save_trade, seed_trades
from jeflink.common.validators import validate_public_text
from jeflink.zones.models import Zone
from jeflink.zones.services import save_zone, seed_zones
from jeflink.zones.tests.factories import CityFactory

REFUSES = [
    ("Appelez le 77 123 45 67", "contains_phone"),
    ("Écrivez au +221771234567", "contains_phone"),
    ("Au 33 820 12 34", "contains_phone"),
    ("Fixe : 338201234", "contains_phone"),
    ("Fixe 30.820.12.34", "contains_phone"),
    ("Fixe +221 33 820 12 34", "contains_phone"),
    ("https://exemple.com/plomberie", "contains_url"),
    ("Sur www.plombier-dakar.sn", "contains_url"),
    ("Voir plombier.shop", "contains_url"),
    ("plombier-dakar.com", "contains_url"),
    ("Site.COM", "contains_url"),
    ("Dakar.sn", "contains_url"),
    ("insta : @plombier_ouakam", "contains_handle"),
    ("@plombier", "contains_handle"),
    ("ecrire a nom@exemple", "contains_handle"),
]

ACCEPTES = [
    "Unité 15",
    "Sacré-Cœur 3",
    "PA",
    "Parcelles Assainies",
    "Yoff Virage",
    "M.Diop, etc. et autres. Voilà.",
    "Prix à partir de 15 000 F, 24 rues par jour.",
    "Dakar. Les rues sont étroites.",
    "Fuite d'eau, WC bouché",
    "Cité Keur Gorgui, villa 330",
    "Zone 33, 820 mètres du rond-point",
]


@pytest.mark.parametrize(("text", "code"), REFUSES)
def test_refuse(text, code):
    with pytest.raises(ValidationError) as exc:
        validate_public_text(text)
    assert exc.value.code == code


@pytest.mark.parametrize("text", ACCEPTES)
def test_accepte(text):
    validate_public_text(text)


# --- Appliqué aux noms, titres, descriptions et alias (N6) -------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize(
    "field",
    [
        "name_fr",
        "name_wo",
        "short_description_fr",
        "short_description_wo",
        "seo_title_fr",
        "seo_title_wo",
    ],
)
def test_champs_publics_d_un_metier(field):
    data = {"slug": "vitrier", "name_fr": "Vitrerie", field: "Appelez 77 123 45 67"}
    with pytest.raises(ValidationError) as exc:
        save_trade(trade=Trade(**data))
    assert field in exc.value.error_dict


@pytest.mark.django_db
def test_alias_de_metier_refuse_et_accepte():
    with pytest.raises(ValidationError) as exc:
        save_trade(trade=Trade(slug="vitrier", name_fr="Vitrerie", aliases=["vitre", "@vitrier"]))
    assert "aliases" in exc.value.error_dict
    trade = save_trade(trade=Trade(slug="vitrier", name_fr="Vitrerie", aliases=["Unité 15", "PA"]))
    assert trade.aliases == ["Unité 15", "PA"]


@pytest.mark.django_db
def test_service_nom_et_alias():
    trade = save_trade(trade=Trade(slug="vitrier", name_fr="Vitrerie"))
    for kwargs, field in (
        ({"name_fr": "Pose, voir plombier.shop"}, "name_fr"),
        ({"name_fr": "Pose", "aliases": ["33 820 12 34"]}, "aliases"),
    ):
        with pytest.raises(ValidationError) as exc:
            save_service(service=Service(trade=trade, slug="pose", **kwargs))
        assert field in exc.value.error_dict


@pytest.mark.django_db
def test_nom_et_alias_de_zone():
    from django.contrib.gis.geos import Point

    city = CityFactory()
    center = Point(-17.4, 14.7, srid=4326)
    with pytest.raises(ValidationError) as exc:
        save_zone(zone=Zone(city=city, slug="x", name="Ouakam www.x.sn", center=center))
    assert "name" in exc.value.error_dict
    with pytest.raises(ValidationError) as exc:
        save_zone(zone=Zone(city=city, slug="x", name="Ouakam", aliases=["@ouakam"], center=center))
    assert "aliases" in exc.value.error_dict
    zone = save_zone(
        zone=Zone(city=city, slug="x", name="Sacré-Cœur", aliases=["Sacré-Cœur 3"], center=center)
    )
    assert zone.aliases == ["Sacré-Cœur 3"]


@pytest.mark.django_db
def test_les_donnees_de_depart_passent_toujours():
    trades, _ = seed_trades()
    assert trades > 0
    assert seed_zones(open_trades=True) > 0
