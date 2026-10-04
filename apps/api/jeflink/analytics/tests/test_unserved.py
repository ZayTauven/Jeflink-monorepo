import pytest
from django.contrib.auth.models import Group
from django.urls import reverse

from jeflink.accounts.models import User
from jeflink.analytics.models import UnservedDemand
from jeflink.analytics.services import UNSERVED_REASONS, record_unserved

pytestmark = pytest.mark.django_db


def test_enregistre_un_signal_sans_identifiant_d_utilisateur():
    signal = record_unserved(
        reason="trade_not_in_zone", channel="web", trade_slug="plomberie", zone_slug="ouakam"
    )
    assert (signal.trade_slug, signal.zone_slug, signal.reason) == (
        "plomberie",
        "ouakam",
        "trade_not_in_zone",
    )
    names = {field.name for field in UnservedDemand._meta.get_fields()}
    assert not {"user", "client", "owner", "phone", "location", "landmark"} & names


def test_hors_zone_garde_la_zone_la_plus_proche_et_la_distance():
    signal = record_unserved(
        reason="out_of_area",
        channel="app",
        trade_slug="plomberie",
        nearest_zone_slug="ouakam",
        distance_km=12,
    )
    assert (signal.nearest_zone_slug, signal.distance_km) == ("ouakam", 12)


def test_quartier_inconnu_garde_le_texte_normalise():
    signal = record_unserved(
        reason="zone_unknown", channel="web", trade_slug="plomberie", zone_text="keur massar"
    )
    assert signal.zone_text == "keur massar"


def test_le_texte_n_est_garde_que_pour_zone_unknown():
    signal = record_unserved(
        reason="no_quote", channel="web", trade_slug="plomberie", zone_slug="ouakam", zone_text="x"
    )
    assert signal.zone_text == ""


def test_metier_inconnu_est_normalise_et_les_numeros_sont_ecartes():
    ok = record_unserved(reason="trade_not_found", channel="app", trade_slug="Vitrier  Pro")
    assert ok.trade_slug == "vitrier-pro"
    with_phone = record_unserved(
        reason="trade_not_found", channel="app", trade_slug="appelez 771234567"
    )
    assert with_phone.trade_slug == ""


def test_motif_ou_canal_inconnu_refuse():
    with pytest.raises(ValueError):
        record_unserved(reason="zone_ambiguous", channel="web")
    with pytest.raises(ValueError):
        record_unserved(reason="no_quote", channel="sms")


def test_les_motifs_sont_ceux_d_availability_et_deux_de_plus():
    assert {"no_provider", "no_quote"} <= UNSERVED_REASONS
    assert "zone_ambiguous" not in UNSERVED_REASONS and "available" not in UNSERVED_REASONS


@pytest.fixture(autouse=True)
def _second_facteur_valide(monkeypatch):
    monkeypatch.setattr("jeflink.accounts.admin_site.admin_mfa_valid", lambda request: True)


def test_admin_en_lecture_seule(client):
    user = User.objects.create_user("+221770000602", is_staff=True)
    user.groups.add(Group.objects.get(name="Saisie catalogue"))
    client.force_login(user)
    signal = record_unserved(reason="no_quote", channel="web", trade_slug="plomberie")
    assert client.get(reverse("admin:analytics_unserveddemand_changelist")).status_code == 200
    assert client.get(reverse("admin:analytics_unserveddemand_add")).status_code == 403
    change = reverse("admin:analytics_unserveddemand_change", args=[signal.pk])
    response = client.post(change, {"reason": "autre"})
    assert response.status_code == 403
    assert (
        client.post(reverse("admin:analytics_unserveddemand_delete", args=[signal.pk])).status_code
        == 403
    )
