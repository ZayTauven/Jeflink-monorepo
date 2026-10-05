"""API du portefeuille pro (spec 005, tâche 8) : résumé, historique, détail, déclarations.
Pour chaque endpoint : autorisé, refusé (autre pro : 404 ; sans rôle : 403) et invalide."""

import uuid
from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from jeflink.accounts.tests.factories import CompleteUserFactory
from jeflink.bookings.tests.test_pro_api import pro_api
from jeflink.catalog.tests.factories import TradeFactory
from jeflink.payments import services
from jeflink.payments.models import PaymentIntent, SettlementChannel
from jeflink.providers.models import Provider
from jeflink.providers.tests.factories import VerifiedProviderFactory
from jeflink.requests.tests.test_requests_api import bearer
from jeflink.wallet.models import CommissionRate
from jeflink.wallet.services import waive_commission
from jeflink.wallet.tests.test_commission import close, commission_of, completed

from .test_settlements import owe

pytestmark = pytest.mark.django_db
REFERENCE = "T_8XQ4L2ZK9P"


@pytest.fixture
def wave():
    return SettlementChannel.objects.create(
        slug="wave",
        gateway="manual_mobile_money",
        label_fr="Wave",
        account_display="77 000 00 00",
        instructions_fr="Envoyez au numéro marchand, puis déclarez le paiement.",
    )


@pytest.fixture
def provider():
    return VerifiedProviderFactory(trades=[TradeFactory(slug="plombier-test")])


def body(**overrides):
    return {
        "channel": "wave",
        "amount_xof": 1_000,
        "reference": REFERENCE,
        "paid_at": (timezone.now() - timedelta(minutes=5)).isoformat(),
    } | overrides


def post_settlement(api, data, key=None):
    return api.post(
        reverse("pro-wallet-settlements"),
        data,
        format="json",
        HTTP_IDEMPOTENCY_KEY=key or uuid.uuid4().hex,
    )


# --- Résumé ------------------------------------------------------------------------------------


def test_le_resume_montre_la_dette_le_taux_et_les_canaux(api_client, provider, wave):
    SettlementChannel.objects.create(slug="caisse", gateway="cash", label_fr="Bureau")
    SettlementChannel.objects.create(
        slug="ancien", gateway="manual_mobile_money", label_fr="Ancien", is_active=False
    )
    trade = provider.trades.first()
    CommissionRate.objects.create(
        trade=trade, rate_bps=800, cap_xof=None, valid_from=timezone.now() + timedelta(days=30)
    )
    owe(provider, 12_000)

    data = pro_api(api_client, provider).get(reverse("pro-wallet")).json()
    assert {k: data[k] for k in ("due_xof", "pending_xof", "effective_due_xof", "state")} == {
        "due_xof": 12_000,
        "pending_xof": 0,
        "effective_due_xof": 12_000,
        "state": "alert",
    }
    assert (data["alert_threshold_xof"], data["block_threshold_xof"]) == (10_000, 25_000)
    assert data["rates"] == [
        {
            "trade_slug": "plombier-test",
            "rate_bps": 1_000,
            "cap_xof": 20_000,
            "next": {
                "rate_bps": 800,
                "cap_xof": None,
                "valid_from": data["rates"][0]["next"]["valid_from"],
            },
        }
    ]
    assert [c["slug"] for c in data["channels"]] == ["wave"]
    assert data["channels"][0]["account_display"] == "77 000 00 00"


def test_un_pro_suspendu_lit_son_portefeuille_et_regle(api_client, provider, wave):
    owe(provider, 1_000)
    Provider.objects.filter(pk=provider.pk).update(status=Provider.Status.SUSPENDED)
    api = pro_api(api_client, provider)
    assert api.get(reverse("pro-wallet")).status_code == 200
    assert post_settlement(api, body()).status_code == 201


def test_sans_role_de_gerant_403_et_sans_session_401(api_client):
    response = bearer(api_client, CompleteUserFactory()).get(reverse("pro-wallet"))
    assert (response.status_code, response.json()["code"]) == (403, "role_required")
    api_client.credentials()
    assert api_client.get(reverse("pro-wallet")).status_code == 401


# --- Historique --------------------------------------------------------------------------------


def test_l_historique_liste_commissions_et_reglements_du_pro_seulement(api_client, wave):
    _, booking = completed()
    commission = commission_of(close(booking))
    provider = commission.provider
    other = VerifiedProviderFactory()
    owe(other, 5_000)
    intent = services.declare_settlement(
        provider=provider,
        actor=provider.owner,
        channel=wave,
        amount_xof=1_500,
        reference=REFERENCE,
        paid_at=timezone.now(),
        payer_last4="",
        idempotency_key=uuid.uuid4().hex,
    ).intent
    services.confirm_settlement(intent=intent, operator=CompleteUserFactory(), received_xof=1_500)

    api = pro_api(api_client, provider)
    results = api.get(reverse("pro-wallet-entries")).json()["results"]
    assert [(e["kind"], e["effect"], e["amount_xof"]) for e in results] == [
        ("settlement", "decrease", 1_500),
        ("commission", "increase", 1_500),
    ]
    assert results[1]["booking"]["id"] == str(booking.public_id)
    assert results[1]["booking"]["trade_slug"] == booking.request.trade.slug
    assert results[0]["booking"] is None


def test_le_detail_d_une_commission_montre_assiette_taux_et_avoirs(api_client):
    _, booking = completed()
    commission = commission_of(close(booking))
    waive_commission(
        commission=commission,
        amount_xof=500,
        reason_code="dispute_refund",
        note="Le pro a remboursé une partie au client.",
        operator=CompleteUserFactory(),
        key=uuid.uuid4().hex,
    )
    api = pro_api(api_client, commission.provider)
    url = reverse("pro-wallet-entry", args=[commission.ledger_transaction.public_id])
    data = api.get(url).json()

    assert data["commission"] == {
        "base_xof": 15_000,
        "rate_bps": 1_000,
        "cap_xof": 20_000,
        "amount_xof": 1_500,
        "completion_method": "",
    }
    assert [(r["amount_xof"], r["reason_code"]) for r in data["reversals"]] == [
        (500, "dispute_refund")
    ]
    assert "remboursé" not in api.get(url).content.decode()  # la note reste à l'Ops

    stranger = pro_api(api_client, VerifiedProviderFactory())
    response = stranger.get(url)
    assert (response.status_code, response.json()["code"]) == (404, "not_found")


# --- Déclarations ------------------------------------------------------------------------------


def test_declarer_201_puis_rejeu_200_et_autre_corps_409(api_client, provider, wave):
    owe(provider, 4_500)
    api = pro_api(api_client, provider)
    key = uuid.uuid4().hex
    sent = body(amount_xof=4_500, payer_last4="0542")  # l'app renvoie le même corps
    first = post_settlement(api, sent, key)
    again = post_settlement(api, sent, key)
    other = post_settlement(api, sent | {"amount_xof": 4_000}, key)

    assert (first.status_code, again.status_code) == (201, 200)
    assert first.json()["id"] == again.json()["id"]
    assert (other.status_code, other.json()["code"]) == (409, "idempotency_key_reused")
    data = first.json()
    assert (data["status"], data["reference_hint"], data["can_cancel"]) == (
        "declared",
        "ZK9P",
        True,
    )
    text = first.content.decode()
    assert REFERENCE not in text and "0542" not in text
    listed = api.get(reverse("pro-wallet-settlements")).json()["results"]
    assert [s["id"] for s in listed] == [data["id"]]


@pytest.mark.parametrize(
    ("overrides", "status", "code"),
    [
        ({"amount_xof": 5_000}, 422, "settlement_exceeds_due"),
        ({"reference": "771234567"}, 422, "settlement_reference_invalid"),
        ({"payer_last4": "12"}, 422, "payer_last4_invalid"),
        ({"channel": "inconnu"}, 422, "channel_inactive"),
        ({"paid_at": "2020-01-01T00:00:00Z"}, 422, "paid_at_invalid"),
        ({"amount_xof": "beaucoup"}, 400, None),
    ],
)
def test_declaration_invalide(api_client, provider, wave, overrides, status, code):
    owe(provider, 4_500)
    response = post_settlement(pro_api(api_client, provider), body(**overrides))
    assert response.status_code == status
    if code:
        assert response.json()["code"] == code
    assert not PaymentIntent.objects.exists()


def test_declaration_sans_cle_d_idempotence_400(api_client, provider, wave):
    owe(provider, 4_500)
    response = pro_api(api_client, provider).post(
        reverse("pro-wallet-settlements"), body(), format="json"
    )
    assert (response.status_code, response.json()["code"]) == (400, "idempotency_key_required")


def test_retirer_puis_corriger_une_declaration(api_client, provider, wave):
    owe(provider, 4_500)
    api = pro_api(api_client, provider)
    created = post_settlement(api, body(amount_xof=4_500)).json()

    cancel = api.post(reverse("pro-wallet-settlement-cancel", args=[created["id"]]))
    assert (cancel.status_code, cancel.json()["status"]) == (200, "cancelled")
    again = api.post(reverse("pro-wallet-settlement-cancel", args=[created["id"]]))
    assert (again.status_code, again.json()["code"]) == (409, "settlement_not_pending")

    second = post_settlement(api, body(amount_xof=4_500, reference="T_TYPO00001")).json()
    intent = PaymentIntent.objects.get(public_id=second["id"])
    services.request_correction(
        intent=intent, operator=CompleteUserFactory(), reason="reference_not_found"
    )
    url = reverse("pro-wallet-settlement-correct", args=[second["id"]])
    # Nouvelle référence : celle de la déclaration retirée ne resert pas au même pro.
    fixed = body(amount_xof=4_500, reference="T_FIXED00001")
    fixed.pop("channel")
    corrected = api.post(url, fixed, format="json")
    assert (corrected.status_code, corrected.json()["status"]) == (200, "declared")
    refused = api.post(url, fixed, format="json")
    assert (refused.status_code, refused.json()["code"]) == (409, "settlement_not_correctable")


def test_les_declarations_d_un_autre_pro_repondent_404(api_client, provider, wave):
    owe(provider, 4_500)
    created = post_settlement(pro_api(api_client, provider), body()).json()
    stranger = pro_api(api_client, VerifiedProviderFactory())
    for url in (
        reverse("pro-wallet-settlement-cancel", args=[created["id"]]),
        reverse("pro-wallet-settlement-correct", args=[created["id"]]),
    ):
        response = stranger.post(url, body(), format="json")
        assert (response.status_code, response.json()["code"]) == (404, "not_found")
    assert stranger.get(reverse("pro-wallet-settlements")).json()["results"] == []
