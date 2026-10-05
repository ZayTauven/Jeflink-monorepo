"""Statistiques publiques (spec 006, tâche 5) : seuils, arrondis, exclusions, règles, API."""

from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from jeflink.accounts.tests.factories import CompleteUserFactory
from jeflink.analytics import selectors
from jeflink.analytics.api.views import PublicStatsView
from jeflink.analytics.selectors import public_rules, public_stats
from jeflink.bookings.selectors import public_closed_bookings
from jeflink.catalog.tests.factories import TradeFactory
from jeflink.common.errors import DomainError
from jeflink.providers.models import Provider
from jeflink.providers.selectors import public_verified_providers
from jeflink.providers.tests.factories import ProviderFactory, VerifiedProviderFactory
from jeflink.reviews.selectors import public_counted_reviews
from jeflink.zones.tests.factories import ZoneFactory

from .factories import closed_booking, review_for

pytestmark = pytest.mark.django_db

PUBLIC = "public, max-age=300, stale-while-revalidate=86400"


class FakeCount:
    """Remplace un sélecteur quand seul le nombre compte (évite de créer 50 réservations)."""

    def __init__(self, count: int, pros: int = 10):
        self._count = count
        self._pros = pros

    def count(self) -> int:
        return self._count

    def order_by(self, *args):
        return self

    def values(self, *args):
        return FakeCount(self._pros)

    def distinct(self):
        return self


@pytest.fixture
def low_thresholds(settings, monkeypatch):
    """Seuils bas pour tester avec quelques lignes ; les valeurs réelles ont leur propre test."""
    settings.PUBLIC_STATS_MIN_MISSIONS = 10
    settings.PUBLIC_STATS_MIN_REVIEWS = 3
    settings.PUBLIC_STATS_MIN_PROS = 2
    settings.PUBLIC_STATS_MIN_PROS_FILTERED = 2
    settings.PUBLIC_STATS_MIN_RATED_PROS = 3
    monkeypatch.setattr(selectors, "ROUND_TO", 1)  # les arrondis ont leurs propres tests


@pytest.fixture
def terrain():
    trade = TradeFactory(slug="plombier")
    zone = ZoneFactory(slug="ouakam", trades=[trade])
    return trade, zone


# --- Réglages et règles -----------------------------------------------------------------------


def test_seuils_par_defaut_de_la_spec(settings):
    assert settings.PUBLIC_STATS_MIN_MISSIONS == 50
    assert settings.PUBLIC_STATS_MIN_REVIEWS == 20
    assert settings.PUBLIC_STATS_MIN_PROS == 5
    assert settings.PUBLIC_STATS_MIN_PROS_FILTERED == 3
    assert settings.PUBLIC_STATS_MIN_RATED_PROS == 3


def test_regles_lues_dans_les_reglages_existants(settings):
    settings.QUOTE_MAX_ACTIVE = 4
    settings.BOOKING_DISPUTE_WINDOW = timedelta(hours=36)
    settings.BOOKING_CONFIRM_TTL = timedelta(hours=6)
    settings.BOOKING_CONFIRM_TTL_URGENT = timedelta(minutes=90)
    settings.BOOKING_CONFIRM_QUIET_HOURS = (22, 6)
    assert public_rules() == {
        "max_quotes_per_request": 4,
        "dispute_window_hours": 36,
        "pro_confirm_hours": 6,
        "pro_confirm_hours_urgent": 1.5,
        "quiet_hours": {"start": 22, "end": 6},
    }


def test_regles_par_defaut_egales_aux_reglages(settings):
    rules = public_rules()
    assert rules["max_quotes_per_request"] == settings.QUOTE_MAX_ACTIVE
    assert rules["dispute_window_hours"] * 3600 == settings.BOOKING_DISPUTE_WINDOW.total_seconds()
    assert rules["pro_confirm_hours"] * 3600 == settings.BOOKING_CONFIRM_TTL.total_seconds()
    assert (
        rules["pro_confirm_hours_urgent"] * 3600
        == settings.BOOKING_CONFIRM_TTL_URGENT.total_seconds()
    )
    start, end = settings.BOOKING_CONFIRM_QUIET_HOURS
    assert rules["quiet_hours"] == {"start": start, "end": end}


# --- Base vide --------------------------------------------------------------------------------


def test_base_vide_tout_est_null_et_les_regles_restent():
    stats = public_stats()
    assert stats["missions_completed"] is None
    assert stats["rating"] is None
    assert stats["verified_pros"] is None
    assert stats["rules"] == public_rules()


# --- Missions : seuil et arrondi ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("count", "expected"),
    [(0, None), (49, None), (50, 50), (59, 50), (60, 60), (123, 120)],
)
def test_missions_seuil_et_dizaine_inferieure(monkeypatch, count, expected):
    monkeypatch.setattr(selectors, "public_closed_bookings", lambda **kw: FakeCount(count))
    assert public_stats()["missions_completed"] == expected


def test_missions_ne_comptent_que_les_reservations_cloturees(terrain, low_thresholds):
    trade, zone = terrain
    closed_booking(trade=trade, zone=zone)
    closed_booking(trade=trade, zone=zone, status="completed")
    closed_booking(trade=trade, zone=zone, status="cancelled")
    assert public_closed_bookings().count() == 1


def test_missions_excluent_pros_de_demo_et_comptes_de_revue(terrain):
    trade, zone = terrain
    closed_booking(trade=trade, zone=zone)
    demo = closed_booking(trade=trade, zone=zone)
    Provider.objects.filter(pk=demo.provider_id).update(is_demo=True)
    client = closed_booking(trade=trade, zone=zone)
    type(client.client).objects.filter(pk=client.client_id).update(is_review_account=True)
    owner = closed_booking(trade=trade, zone=zone)
    type(owner.client).objects.filter(pk=owner.provider.owner_id).update(is_review_account=True)
    assert public_closed_bookings().count() == 1


def test_missions_filtrees_par_metier_et_par_zone_de_la_demande(terrain):
    trade, zone = terrain
    other_trade = TradeFactory(slug="electricien")
    other_zone = ZoneFactory(slug="pikine", trades=[trade, other_trade])
    closed_booking(trade=trade, zone=zone)
    closed_booking(trade=trade, zone=other_zone)
    closed_booking(trade=other_trade, zone=zone)
    assert public_closed_bookings().count() == 3
    assert public_closed_bookings(trade=trade).count() == 2
    assert public_closed_bookings(zone=zone).count() == 2
    assert public_closed_bookings(trade=trade, zone=zone).count() == 1


# --- Note moyenne : seuil, 3 pros distincts, exclusions -------------------------------------------


def rated(trade, zone, ratings, *, providers=None):
    """Un avis par note ; ``providers`` fixe le pro de chaque avis (sinon un pro par avis)."""
    out = []
    for index, rating in enumerate(ratings):
        provider = providers[index] if providers else None
        out.append(review_for(closed_booking(trade=trade, zone=zone, provider=provider), rating))
    return out


def test_note_sous_le_seuil_d_avis(terrain, low_thresholds):
    trade, zone = terrain
    rated(trade, zone, [5, 4])
    assert public_stats()["rating"] is None


def test_note_au_seuil_arrondie_a_une_decimale(terrain, low_thresholds):
    trade, zone = terrain
    rated(trade, zone, [5, 4, 4])
    assert public_stats()["rating"] == {"average": 4.3, "count": 3}


def test_note_refusee_quand_les_avis_viennent_de_moins_de_3_pros(terrain, low_thresholds):
    trade, zone = terrain
    pros = [VerifiedProviderFactory(trades=[trade], zones=[zone]) for _ in range(2)]
    rated(trade, zone, [5, 5, 5, 4], providers=[pros[0], pros[0], pros[1], pros[1]])
    assert public_counted_reviews().count() == 4  # assez d'avis, mais deux pros seulement
    assert public_stats()["rating"] is None
    assert public_stats(trade=trade)["rating"] is None
    assert public_stats(trade=trade, zone=zone)["rating"] is None


def test_note_jamais_avec_un_quartier(terrain, low_thresholds):
    trade, zone = terrain
    other = ZoneFactory(slug="pikine", trades=[trade])
    rated(trade, zone, [5, 5, 5])
    pro = VerifiedProviderFactory(trades=[trade], zones=[other])
    rated(trade, other, [1, 1, 1], providers=[pro, pro, pro])
    # Avec un quartier, null même au-dessus de tous les seuils : la différence de deux filtres
    # isolerait la note d'un pro.
    assert public_stats(trade=trade, zone=zone)["rating"] is None
    assert public_stats(trade=trade, zone=other)["rating"] is None
    assert public_stats(trade=trade)["rating"] is not None
    assert public_stats()["rating"]["count"] == 6  # 3 sur 6 pour un pro : permis


def test_note_null_si_un_pro_pese_plus_de_la_moitie_des_avis(terrain, low_thresholds):
    trade, zone = terrain
    big = VerifiedProviderFactory(trades=[trade], zones=[zone])
    rated(trade, zone, [5, 5, 5], providers=[big, big, big])  # 3 avis d'un même pro
    rated(trade, zone, [4, 4])  # 2 pros de plus : 3 pros distincts au total, 5 avis
    assert public_counted_reviews().count() == 5
    assert public_stats()["rating"] is None  # 3 / 5 = 60 %
    rated(trade, zone, [4, 4])  # 3 sur 7 : 43 %
    assert public_stats()["rating"] is not None
    rated(trade, zone, [3], providers=[big])  # 4 sur 8 : exactement 50 %, permis
    assert public_stats()["rating"] is not None
    rated(trade, zone, [3], providers=[big])  # 5 sur 9 : plus de la moitié
    assert public_stats()["rating"] is None


def test_note_count_arrondi_a_la_dizaine(terrain, low_thresholds, monkeypatch):
    trade, zone = terrain
    rated(trade, zone, [5, 4, 4])
    monkeypatch.setattr(selectors, "ROUND_TO", 2)
    assert public_stats()["rating"] == {"average": 4.3, "count": 2}
    monkeypatch.setattr(selectors, "ROUND_TO", 10)
    assert public_stats()["rating"]["count"] == 0  # le vrai seuil (20) garantit au moins 20


def test_zone_sans_metier_refusee(terrain):
    _, zone = terrain
    with pytest.raises(DomainError) as exc:
        public_stats(zone=zone)
    assert (exc.value.code, exc.value.status_code) == ("zone_requires_trade", 400)


def test_missions_null_sous_3_pros_distincts(monkeypatch):
    monkeypatch.setattr(selectors, "public_closed_bookings", lambda **kw: FakeCount(80, pros=2))
    assert public_stats()["missions_completed"] is None
    monkeypatch.setattr(selectors, "public_closed_bookings", lambda **kw: FakeCount(80, pros=3))
    assert public_stats()["missions_completed"] == 80


def test_missions_d_un_seul_pro_jamais_exposees(terrain, settings):
    trade, zone = terrain
    settings.PUBLIC_STATS_MIN_MISSIONS = 2
    pro = VerifiedProviderFactory(trades=[trade], zones=[zone])
    for _ in range(2):
        closed_booking(trade=trade, zone=zone, provider=pro)
    assert public_closed_bookings(trade=trade, zone=zone).count() == 2
    assert public_stats(trade=trade, zone=zone)["missions_completed"] is None
    assert public_stats(trade=trade)["missions_completed"] is None


def test_la_borne_de_dominance_est_la_moitie(settings):
    assert settings.PUBLIC_STATS_MAX_PRO_SHARE == 0.5
    assert settings.PUBLIC_STATS_MIN_MISSION_PROS == 3


def test_note_exclut_masques_non_publies_demo_et_comptes_de_revue(terrain, low_thresholds):
    trade, zone = terrain
    rated(trade, zone, [5, 5, 5])
    hidden = review_for(
        closed_booking(trade=trade, zone=zone), 1, hidden_at=timezone.now(), hidden_reason="abuse"
    )
    unpublished = review_for(closed_booking(trade=trade, zone=zone), 1, published_at=None)
    demo = review_for(closed_booking(trade=trade, zone=zone), 1)
    Provider.objects.filter(pk=demo.provider_id).update(is_demo=True)
    reviewer = review_for(closed_booking(trade=trade, zone=zone), 1)
    type(reviewer.author).objects.filter(pk=reviewer.author_id).update(is_review_account=True)
    owner = review_for(closed_booking(trade=trade, zone=zone), 1)
    type(owner.author).objects.filter(pk=owner.provider.owner_id).update(is_review_account=True)
    assert {hidden.pk, unpublished.pk}.isdisjoint(public_counted_reviews())
    assert public_stats()["rating"] == {"average": 5.0, "count": 3}


# --- Pros vérifiés ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("count", "expected"),
    [(4, None), (5, 5), (9, 9), (10, 10), (19, 10), (20, 20), (27, 20)],
)
def test_pros_seuil_sans_filtre_exact_jusqu_a_9_puis_dizaine(monkeypatch, count, expected):
    monkeypatch.setattr(selectors, "public_verified_providers", lambda **kw: FakeCount(count))
    assert public_stats()["verified_pros"] == expected


@pytest.mark.parametrize(("count", "expected"), [(2, None), (3, 3), (9, 9), (14, 10)])
def test_pros_seuil_avec_filtre_de_3(monkeypatch, terrain, count, expected):
    trade, zone = terrain
    monkeypatch.setattr(selectors, "public_verified_providers", lambda **kw: FakeCount(count))
    assert public_stats(trade=trade)["verified_pros"] == expected
    assert public_stats(trade=trade, zone=zone)["verified_pros"] == expected


def test_pros_seuil_sans_filtre_est_de_5_avec_les_reglages_par_defaut(terrain):
    trade, zone = terrain
    for _ in range(4):
        VerifiedProviderFactory(trades=[trade], zones=[zone])
    assert public_stats()["verified_pros"] is None
    assert public_stats(trade=trade)["verified_pros"] == 4  # filtre : seuil de 3
    VerifiedProviderFactory(trades=[trade], zones=[zone])
    assert public_stats()["verified_pros"] == 5


def test_pros_ne_comptent_que_les_fiches_verifiees_hors_demo_et_revue(terrain):
    trade, zone = terrain
    VerifiedProviderFactory(trades=[trade], zones=[zone])
    ProviderFactory(trades=[trade], zones=[zone])  # en attente
    ProviderFactory(trades=[trade], zones=[zone], status=Provider.Status.SUSPENDED)
    VerifiedProviderFactory(trades=[trade], zones=[zone], is_demo=True)
    reviewer = VerifiedProviderFactory(
        trades=[trade], zones=[zone], owner=CompleteUserFactory(is_review_account=True)
    )
    assert reviewer.owner.is_review_account
    assert public_verified_providers().count() == 1


def test_pros_filtres_par_metier_et_par_zone_de_la_fiche(terrain):
    trade, zone = terrain
    other_trade = TradeFactory(slug="electricien")
    other_zone = ZoneFactory(slug="pikine")
    VerifiedProviderFactory(trades=[trade], zones=[zone])
    VerifiedProviderFactory(trades=[trade, other_trade], zones=[zone, other_zone])
    VerifiedProviderFactory(trades=[other_trade], zones=[other_zone])
    assert public_verified_providers().count() == 3
    assert public_verified_providers(trade=trade).count() == 2
    assert public_verified_providers(zone=other_zone).count() == 2
    assert public_verified_providers(trade=trade, zone=other_zone).count() == 1


# --- API ------------------------------------------------------------------------------------------


def get_stats(client, **params):
    return client.get(reverse("stats"), params)


def test_vue_publique_limitee_et_sans_authentification(settings):
    assert PublicStatsView.rate_limit_scope == "catalog_read" in settings.IP_RATE_LIMITS
    assert PublicStatsView.authentication_classes == []


def test_api_reponse_publique_cacheable(api_client, terrain):
    response = get_stats(api_client)
    assert response.status_code == 200
    assert response["Cache-Control"] == PUBLIC
    assert response["ETag"]
    assert response.json() == {
        "missions_completed": None,
        "rating": None,
        "verified_pros": None,
        "rules": {
            "max_quotes_per_request": 3,
            "dispute_window_hours": 48,
            "pro_confirm_hours": 4,
            "pro_confirm_hours_urgent": 1,
            "quiet_hours": {"start": 21, "end": 7},
        },
    }


def test_api_chiffres_au_dessus_des_seuils(api_client, terrain, low_thresholds):
    trade, zone = terrain
    rated(trade, zone, [5, 4, 4])
    data = get_stats(api_client, trade="plombier", zone="ouakam").json()
    assert data["missions_completed"] is None  # 3 missions, seuil de 10
    assert data["rating"] is None  # jamais avec un quartier
    assert data["verified_pros"] == 3
    data = get_stats(api_client, trade="plombier").json()
    assert data["rating"] == {"average": 4.3, "count": 3}


def test_api_aucun_nom_ni_identifiant(api_client, terrain, low_thresholds):
    trade, zone = terrain
    rated(trade, zone, [5, 4, 4])
    response = get_stats(api_client)
    data = response.json()
    assert set(data) == {"missions_completed", "rating", "verified_pros", "rules"}
    assert set(data["rating"]) == {"average", "count"}
    body = response.content.decode().lower()
    for forbidden in ("public_id", "business_name", "phone", "owner", "client", "uuid", 'id":'):
        assert forbidden not in body


def test_api_304_avec_etag(api_client, terrain):
    first = get_stats(api_client)
    second = api_client.get(reverse("stats"), headers={"If-None-Match": first["ETag"]})
    assert second.status_code == 304


@pytest.mark.parametrize(
    ("params", "code"),
    [
        ({"trade": "inconnu"}, "trade_not_found"),
        ({"trade": "plombier", "zone": "inconnue"}, "zone_not_found"),
        ({"trade": "ferme"}, "trade_not_found"),
        ({"trade": "plombier", "zone": "fermee"}, "zone_not_found"),
    ],
)
def test_api_filtre_inconnu_ou_inactif(api_client, terrain, params, code):
    TradeFactory(slug="ferme", is_active=False)
    ZoneFactory(slug="fermee", is_active=False)
    response = get_stats(api_client, **params)
    assert (response.status_code, response.json()) == (404, {"code": code})


@pytest.mark.parametrize("zone", ["ouakam", "inconnue"])
def test_api_quartier_seul_refuse_en_400(api_client, terrain, zone):
    response = get_stats(api_client, zone=zone)
    assert (response.status_code, response.json()) == (400, {"code": "zone_requires_trade"})


def test_api_filtres_permis(api_client, terrain):
    for params in ({}, {"trade": "plombier"}, {"trade": "plombier", "zone": "ouakam"}):
        assert get_stats(api_client, **params).status_code == 200


def test_api_refuse_les_ecritures(api_client):
    assert api_client.post(reverse("stats"), {}).status_code == 405
