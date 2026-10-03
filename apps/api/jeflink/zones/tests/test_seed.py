"""Données de départ (spec 002) : idempotentes, jamais d'écrasement d'une saisie Ops."""

from io import StringIO

import pytest
from django.core.management import call_command

from jeflink.catalog.models import Service, Trade
from jeflink.catalog.reference_data import TRADES
from jeflink.catalog.selectors import resolve_trade_text
from jeflink.zones.models import Zone
from jeflink.zones.reference_data import ZONES
from jeflink.zones.selectors import resolve_zone_text

pytestmark = pytest.mark.django_db


def seed(*args):
    call_command("seed_reference_data", *args, stdout=StringIO())


def test_deux_fois_sans_doublon_ni_ecrasement():
    seed("--open-trades")
    counts = (Trade.objects.count(), Service.objects.count(), Zone.objects.count())
    assert counts == (6, sum(len(t["services"]) for t in TRADES), 24)
    assert len(ZONES) == 24

    Trade.objects.filter(slug="plombier").update(name_fr="Plomberie et sanitaires", is_active=False)
    pikine = Zone.objects.get(slug="pikine")
    pikine.trades.clear()
    pikine.aliases = ["Thiaroye"]
    pikine.save()

    seed("--open-trades")
    assert (Trade.objects.count(), Service.objects.count(), Zone.objects.count()) == counts
    assert Trade.objects.get(slug="plombier").name_fr == "Plomberie et sanitaires"
    pikine.refresh_from_db()
    assert pikine.aliases == ["Thiaroye"]
    assert not pikine.trades.exists()


def test_metiers_fermes_par_defaut_hors_local():
    seed()  # DJANGO_ENV = test : l'Ops ouvre lui-même les métiers
    assert not Zone.trades.through.objects.exists()


def test_wo_et_prix_vides():
    seed()
    assert not Trade.objects.exclude(name_wo="").exists()
    assert not Service.objects.filter(price_from_xof__isnull=False).exists()


@pytest.mark.parametrize(
    ("texte", "zone"),
    [
        ("PA", "parcelles-assainies"),
        ("parcelle", "parcelles-assainies"),
        ("Sacre Coeur", "sacre-coeur"),
        ("Sicap", "liberte"),
        ("Thiaroye", "pikine"),
        ("Golf Sud", "guediawaye"),
        ("Sandaga", "plateau"),
    ],
)
def test_criteres_de_recherche_des_zones(texte, zone):
    seed()
    assert [z.slug for z in resolve_zone_text(texte)] == [zone]


def test_criteres_de_recherche_des_metiers():
    seed()
    assert [t.slug for t in resolve_trade_text("frigoriste")] == ["climatisation"]
    assert [t.slug for t in resolve_trade_text("frigo")] == ["climatisation", "electromenager"]
    assert [t.slug for t in resolve_trade_text("bricoleur")] == ["petits-travaux"]
