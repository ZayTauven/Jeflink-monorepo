import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from jeflink.catalog.models import Service, Trade
from jeflink.catalog.selectors import active_trade, active_trades, resolve_trade_text
from jeflink.catalog.services import save_service, save_trade
from jeflink.common.errors import DomainError

from .factories import ServiceFactory, TradeFactory

pytestmark = pytest.mark.django_db


def test_save_trade_nettoie_les_alias():
    trade = save_trade(
        trade=Trade(
            slug="plombier", name_fr="Plomberie", aliases=[" WC  qui coule", "", "wc qui coule"]
        )
    )
    assert trade.aliases == ["WC qui coule"]


@pytest.mark.parametrize("slug", ["Plombier", "plom bier", "plombier-", "-plombier", "é", "a--b"])
def test_slug_mal_forme_refuse(slug):
    with pytest.raises(ValidationError) as exc:
        save_trade(trade=Trade(slug=slug, name_fr="X"))
    assert "slug" in exc.value.message_dict


def test_slug_mal_forme_refuse_en_base():
    with pytest.raises(IntegrityError), transaction.atomic():
        Trade.objects.create(slug="Mal Forme", name_fr="X")


def test_slug_reserve_refuse():
    with pytest.raises(ValidationError) as exc:
        save_trade(trade=Trade(slug="connexion", name_fr="Connexion"))
    assert exc.value.error_dict["slug"][0].code == "slug_reserved"


def test_nom_fr_obligatoire_en_base():
    with pytest.raises(IntegrityError), transaction.atomic():
        Trade.objects.create(slug="vide", name_fr="")


def test_slug_fige_apres_creation():
    trade = TradeFactory(slug="plombier")
    trade.slug = "plomberie"
    with pytest.raises(ValidationError) as exc:
        save_trade(trade=trade)
    assert exc.value.error_dict["slug"][0].code == "slug_frozen"
    service = ServiceFactory(trade=trade, slug="fuite")
    service.slug = "fuites"
    with pytest.raises(ValidationError):
        save_service(service=service)


def test_slug_de_service_unique_par_metier():
    trade = TradeFactory()
    ServiceFactory(trade=trade, slug="fuite")
    ServiceFactory(slug="fuite")  # même slug, autre métier : permis
    with pytest.raises(ValidationError):
        save_service(service=Service(trade=trade, slug="fuite", name_fr="Fuite"))


def test_active_trades_ecarte_metiers_et_services_inactifs():
    actif = TradeFactory(position=2)
    TradeFactory(is_active=False)
    premier = TradeFactory(position=1)
    ServiceFactory(trade=actif, slug="ouvert")
    ServiceFactory(trade=actif, slug="ferme", is_active=False)
    trades = list(active_trades())
    assert trades == [premier, actif]
    assert [s.slug for s in trades[1].services.all()] == ["ouvert"]


def test_active_trade_inconnu_ou_inactif():
    TradeFactory(slug="ferme", is_active=False)
    for slug in ("ferme", "inconnu"):
        with pytest.raises(DomainError) as exc:
            active_trade(slug)
        assert (exc.value.code, exc.value.status_code) == ("trade_not_found", 404)


def test_resolve_trade_text_par_alias():
    froid = TradeFactory(
        slug="climatisation",
        name_fr="Froid et climatisation",
        position=3,
        aliases=["frigoriste", "clim", "frigo"],
    )
    menager = TradeFactory(
        slug="electromenager", name_fr="Électroménager", position=4, aliases=["frigo", "machine"]
    )
    assert resolve_trade_text("frigoriste") == [froid]
    # Alias partagé : les deux métiers, le client choisit.
    assert resolve_trade_text("frigo") == [froid, menager]
    assert resolve_trade_text("Électro") == [menager]
    assert resolve_trade_text("vitrier") == []
