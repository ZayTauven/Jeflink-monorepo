"""Taux de commission et calcul (spec 005, tâche 2)."""

import random
from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.auth.models import Group
from django.db import DatabaseError, transaction
from django.db.models import F
from django.utils import timezone

from jeflink.catalog.models import Trade
from jeflink.catalog.services import seed_trades
from jeflink.common.errors import DomainError
from jeflink.trust.models import AuditEvent
from jeflink.wallet.admin import CommissionRateForm
from jeflink.wallet.commission import commission_xof
from jeflink.wallet.models import CommissionRate
from jeflink.wallet.selectors import next_rate_for, rate_for
from jeflink.wallet.services import add_rate, seed_rates

# --- Calcul ------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("base", "rate", "cap", "expected"),
    [
        (30_000, 1_000, None, 3_000),
        (30_000, 1_000, 20_000, 3_000),
        (300_000, 1_000, 20_000, 20_000),  # plafond
        (30_000, 700, 20_000, 2_100),
        (999, 1_000, None, 99),  # 99,9 arrondi à l'entier inférieur, en faveur du pro
        (14, 700, None, 0),  # 0,98
        (0, 1_000, None, 0),
        (30_000, 0, None, 0),
        (10_000, 5_000, None, 5_000),
    ],
)
def test_commission_xof(base, rate, cap, expected):
    result = commission_xof(base, rate, cap)
    assert result == expected
    assert type(result) is int


@pytest.mark.parametrize(
    ("base", "rate", "cap"),
    [
        (30_000.0, 1_000, None),
        (Decimal(30_000), 1_000, None),
        (True, 1_000, None),
        (-1, 1_000, None),
        (30_000, -1, None),
        (30_000, 1_000, 0),
        (30_000, 1_000, 2.5),
    ],
)
def test_commission_xof_refuse_ce_qui_n_est_pas_un_entier(base, rate, cap):
    with pytest.raises(ValueError):
        commission_xof(base, rate, cap)


def test_commission_xof_proprietes_sur_des_assiettes_aleatoires():
    rng = random.Random(5)  # noqa: S311 (suite reproductible, rien de cryptographique)
    for _ in range(500):
        rate = rng.randint(0, 5_000)
        cap = rng.choice([None, rng.randint(1, 50_000)])
        low, high = sorted(rng.randint(0, 2_000_000) for _ in range(2))
        small, large = commission_xof(low, rate, cap), commission_xof(high, rate, cap)
        assert 0 <= small <= low
        assert small <= large  # croissante avec l'assiette
        assert cap is None or large <= cap


# --- Taux applicable ---------------------------------------------------------------------------


@pytest.fixture
def trade():
    seed_trades()
    return Trade.objects.get(slug="plombier")


def at(days: float):
    return timezone.now() + timedelta(days=days)


def rate(trade, bps, valid_from, cap=20_000):
    return CommissionRate.objects.create(
        trade=trade, rate_bps=bps, cap_xof=cap, valid_from=valid_from
    )


@pytest.mark.django_db
def test_le_taux_par_defaut_de_la_migration_s_applique_a_tout_metier(trade):
    applied = rate_for(trade=trade, at=timezone.now())
    assert (applied.trade, applied.rate_bps, applied.cap_xof) == (None, 1_000, 20_000)


@pytest.mark.django_db
def test_le_taux_du_metier_prime_une_fois_en_vigueur(trade):
    own = rate(trade, 700, at(-1))
    rate(None, 1_200, at(-0.5))  # défaut plus récent : ne touche pas le métier

    assert rate_for(trade=trade, at=timezone.now()) == own
    assert rate_for(trade=trade, at=at(-2)).trade is None  # avant son taux propre


@pytest.mark.django_db
def test_un_taux_ajoute_apres_le_devis_ne_change_pas_la_commission(trade):
    quoted_at = timezone.now()
    before = rate_for(trade=trade, at=quoted_at)
    rate(trade, 500, at(1))

    assert rate_for(trade=trade, at=quoted_at) == before
    assert rate_for(trade=trade, at=at(2)).rate_bps == 500


@pytest.mark.django_db
def test_avant_tout_taux_rate_for_rend_none(trade):
    assert rate_for(trade=trade, at=at(-400)) is None  # avant le taux par défaut


@pytest.mark.django_db
def test_le_prochain_taux_annonce(trade):
    assert next_rate_for(trade=trade, at=timezone.now()) is None
    upcoming_default = rate(None, 800, at(10))
    assert next_rate_for(trade=trade, at=timezone.now()) == upcoming_default

    rate(trade, 700, at(-1))
    # Le métier a son taux : un nouveau taux par défaut ne le concerne plus.
    assert next_rate_for(trade=trade, at=timezone.now()) is None
    upcoming_own = rate(trade, 600, at(20))
    assert next_rate_for(trade=trade, at=timezone.now()) == upcoming_own
    assert next_rate_for(trade=None, at=timezone.now()) == upcoming_default


# --- Ajout -------------------------------------------------------------------------------------


@pytest.mark.django_db
def test_add_rate_tout_de_suite_et_audite(trade, user_factory):
    ops = user_factory()
    added = add_rate(
        trade=trade, rate_bps=700, cap_xof=None, valid_from=None, note="", operator=ops
    )

    assert added.created_by == ops
    assert rate_for(trade=trade, at=timezone.now()) == added
    event = AuditEvent.objects.get(action="wallet.rate.added")
    assert event.metadata == {
        "trade": "plombier",
        "rate_bps": 700,
        "cap_xof": None,
        "immediate": True,
    }


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("kwargs", "code"),
    [
        ({"rate_bps": 5_001}, "rate_invalid"),
        ({"rate_bps": 10.0}, "rate_invalid"),
        ({"cap_xof": 0}, "rate_cap_invalid"),
        ({"valid_from": "past"}, "rate_valid_from_past"),
        ({"note": "voir avec le 77 123 45 67"}, "note_invalid"),
    ],
)
def test_add_rate_refuse(trade, user_factory, kwargs, code):
    params = {
        "trade": trade,
        "rate_bps": 700,
        "cap_xof": 20_000,
        "valid_from": at(1),
        "note": "",
        "operator": user_factory(),
    }
    params.update(kwargs)
    if params["valid_from"] == "past":
        params["valid_from"] = at(-1)
    with pytest.raises(DomainError) as exc:
        add_rate(**params)
    assert exc.value.code == code
    assert not CommissionRate.objects.filter(trade=trade).exists()


@pytest.mark.django_db
def test_deux_taux_a_la_meme_date_pour_un_metier_sont_refuses(trade, user_factory):
    when = at(3)
    common = {"trade": trade, "cap_xof": None, "valid_from": when, "note": ""}
    add_rate(rate_bps=700, operator=user_factory(), **common)
    with pytest.raises(DomainError) as exc:
        add_rate(rate_bps=800, operator=user_factory(), **common)
    assert exc.value.code == "rate_duplicate"


@pytest.mark.django_db
def test_un_taux_ne_se_modifie_ni_ne_se_supprime(trade):
    existing = CommissionRate.objects.get(trade__isnull=True)
    # Une réécriture à l'identique ne change rien : permise (rechargement des données de test).
    CommissionRate.objects.filter(pk=existing.pk).update(rate_bps=F("rate_bps"))
    with transaction.atomic(), pytest.raises(DatabaseError, match="immuable"):
        CommissionRate.objects.filter(pk=existing.pk).update(rate_bps=0)
    with transaction.atomic(), pytest.raises(DatabaseError, match="immuable"):
        existing.delete()


# --- Taux de lancement -------------------------------------------------------------------------


@pytest.mark.django_db
def test_seed_rates_cree_les_taux_de_lancement_une_seule_fois():
    seed_trades()
    assert seed_rates() == 3
    assert seed_rates() == 0
    by_trade = dict(
        CommissionRate.objects.filter(trade__isnull=False).values_list("trade__slug", "rate_bps")
    )
    assert by_trade == {"climatisation": 700, "electromenager": 700, "plombier": 700}
    for slug in ("menage", "petits-travaux", "electricien"):
        trade = Trade.objects.get(slug=slug)
        assert rate_for(trade=trade, at=timezone.now()).rate_bps == 1_000


@pytest.mark.django_db
def test_seed_rates_ignore_un_metier_absent():
    assert not Trade.objects.exists()
    assert seed_rates() == 0


# --- Admin -------------------------------------------------------------------------------------


@pytest.mark.django_db
def test_le_formulaire_de_l_admin_applique_les_regles_du_service(trade):
    past = CommissionRateForm(
        data={"trade": trade.pk, "rate_bps": 700, "valid_from": at(-1), "note": ""}
    )
    assert not past.is_valid()
    assert "passé" in str(past.errors)

    now = CommissionRateForm(data={"trade": trade.pk, "rate_bps": 700, "note": ""})
    assert now.is_valid(), now.errors


@pytest.mark.django_db
def test_le_groupe_comptabilite_ajoute_des_taux_sans_les_modifier():
    group = Group.objects.get(name="Comptabilité")
    codenames = set(group.permissions.values_list("codename", flat=True))
    assert {"add_commissionrate", "view_ledgertransaction"} <= codenames
    assert not {"change_commissionrate", "delete_commissionrate"} & codenames
