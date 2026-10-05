"""Socle ``payments`` (spec 005, tâche 4) : interface des passerelles, adaptateurs de la V1,
passerelle factice cantonnée à local et test, canaux de règlement, contraintes des intentions."""

import inspect

import pytest
from django.contrib.admin.sites import site
from django.contrib.auth.models import Group
from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.db import IntegrityError, transaction
from django.test import RequestFactory
from django.utils import timezone

from jeflink.payments.checks import fake_channels
from jeflink.payments.gateways import (
    GatewayOperationUnsupported,
    PaymentGateway,
    check_payment_settings,
    get_gateway,
)
from jeflink.payments.gateways.fake import FakePaymentGateway
from jeflink.payments.models import PaymentIntent, SettlementChannel
from jeflink.payments.services import save_channel
from jeflink.providers.tests.factories import VerifiedProviderFactory
from jeflink.trust.models import AuditEvent

GATEWAYS = ("manual_mobile_money", "cash", "fake")


def intent(**fields) -> PaymentIntent:
    """Intention non enregistrée, telle qu'une passerelle la reçoit."""
    defaults = {
        "purpose": "commission_settlement",
        "gateway": "manual_mobile_money",
        "origin": "pro_declared",
        "status": "declared",
        "declared_xof": 4_500,
        "reference": "T_ABC12345",
        "idempotency_key": "k-1",
    }
    return PaymentIntent(**(defaults | fields))


# --- Registre et environnement -----------------------------------------------------------------


@pytest.mark.parametrize("name", GATEWAYS)
def test_chaque_passerelle_implemente_toute_l_interface(name):
    gateway = get_gateway(name)
    assert isinstance(gateway, PaymentGateway)
    assert gateway.name == name
    assert not inspect.isabstract(type(gateway))


def test_une_passerelle_inconnue_est_refusee():
    with pytest.raises(ImproperlyConfigured):
        get_gateway("wiipay")


@pytest.mark.parametrize("env", ["staging", "production"])
def test_la_passerelle_factice_est_refusee_hors_local_et_test(settings, env):
    settings.DJANGO_ENV = env
    with pytest.raises(ImproperlyConfigured, match="fake"):
        get_gateway("fake")
    settings.PAYMENT_GATEWAY = "fake"
    with pytest.raises(ImproperlyConfigured, match="fake"):
        check_payment_settings()


def test_payment_gateway_doit_etre_connue(settings):
    settings.PAYMENT_GATEWAY = "inconnue"
    with pytest.raises(ImproperlyConfigured, match="inconnu"):
        check_payment_settings()
    settings.PAYMENT_GATEWAY = "manual_mobile_money"
    check_payment_settings()


@pytest.mark.django_db
def test_un_canal_factice_hors_local_et_test_bloque_le_demarrage(settings):
    SettlementChannel.objects.create(slug="factice", gateway="fake", label_fr="Factice")
    assert fake_channels(None, databases=["default"]) == []
    settings.DJANGO_ENV = "production"
    assert [e.id for e in fake_channels(None, databases=["default"])] == ["payments.E001"]


# --- Adaptateurs de la V1 ----------------------------------------------------------------------


def test_mobile_money_ouvre_une_declaration_puis_la_confirme():
    gateway = get_gateway("manual_mobile_money")
    assert gateway.create_intent(intent=intent()).status == "declared"
    assert gateway.confirm(intent=intent(), received_xof=4_500).status == "confirmed"


def test_mobile_money_exige_une_reference():
    with pytest.raises(ValueError):
        get_gateway("manual_mobile_money").create_intent(intent=intent(reference=""))


def test_les_especes_portent_un_recu_et_jamais_une_reference():
    cash = get_gateway("cash")
    ok = intent(gateway="cash", reference="", receipt_number="R-0042")
    assert cash.create_intent(intent=ok).status == "declared"
    with pytest.raises(ValueError):
        cash.create_intent(intent=intent(gateway="cash", receipt_number="R-0042"))
    with pytest.raises(ValueError):
        cash.create_intent(intent=intent(gateway="cash", reference=""))


@pytest.mark.parametrize("name", ["manual_mobile_money", "cash"])
@pytest.mark.parametrize("amount", [0, -1, 4_500.0, True, "4500"])
def test_une_confirmation_exige_un_montant_entier_positif(name, amount):
    with pytest.raises(ValueError):
        get_gateway(name).confirm(intent=intent(), received_xof=amount)


@pytest.mark.parametrize("name", ["manual_mobile_money", "cash"])
@pytest.mark.parametrize("status", ["confirmed", "rejected", "cancelled"])
def test_seule_une_intention_en_attente_se_confirme(name, status):
    with pytest.raises(ValueError):
        get_gateway(name).confirm(intent=intent(status=status), received_xof=4_500)


@pytest.mark.parametrize("name", ["manual_mobile_money", "cash"])
def test_remboursement_versement_et_webhook_ne_sont_pas_offerts_en_v1(name):
    gateway = get_gateway(name)
    with pytest.raises(GatewayOperationUnsupported):
        gateway.refund(intent=intent(), amount_xof=1_000, idempotency_key="r")
    with pytest.raises(GatewayOperationUnsupported):
        gateway.payout(provider=None, amount_xof=1_000, idempotency_key="p")
    with pytest.raises(GatewayOperationUnsupported):
        gateway.verify_webhook(RequestFactory().post("/"))


def test_la_passerelle_factice_offre_tout_sans_reseau():
    FakePaymentGateway.reset()
    fake = get_gateway("fake")
    fake.create_intent(intent=intent())
    fake.confirm(intent=intent(), received_xof=4_500)
    fake.refund(intent=intent(), amount_xof=1_000, idempotency_key="r")
    fake.payout(provider=None, amount_xof=2_000, idempotency_key="p")
    fake.verify_webhook(RequestFactory().post("/"))
    assert [c[0] for c in FakePaymentGateway.calls] == [
        "create_intent", "confirm", "refund", "payout", "verify_webhook",
    ]  # fmt: skip


# --- Canaux de règlement -----------------------------------------------------------------------


@pytest.mark.django_db
def test_un_canal_se_cree_s_audite_et_garde_son_slug(user_factory):
    ops = user_factory()
    channel = save_channel(
        channel=SettlementChannel(
            slug="wave", gateway="manual_mobile_money", label_fr="Wave", account_display="77 000"
        ),
        operator=ops,
    )
    event = AuditEvent.objects.get(action="payments.channel.saved")
    assert event.metadata == {
        "slug": "wave",
        "gateway": "manual_mobile_money",
        "is_active": True,
        "created": True,
    }

    channel.is_active = False
    save_channel(channel=channel, operator=ops)  # désactiver est permis
    channel.slug = "wave-2"
    with pytest.raises(ValidationError):
        save_channel(channel=channel, operator=ops)


@pytest.mark.django_db
def test_un_slug_de_canal_invalide_est_refuse(user_factory):
    with pytest.raises(ValidationError):
        save_channel(
            channel=SettlementChannel(slug="Wave Money", gateway="cash", label_fr="Wave"),
            operator=user_factory(),
        )


def test_un_canal_ne_se_supprime_pas_dans_l_admin(rf):
    channel_admin = site._registry[SettlementChannel]
    assert channel_admin.has_delete_permission(rf.get("/")) is False


@pytest.mark.django_db
def test_la_comptabilite_gere_les_canaux_sans_les_supprimer():
    codenames = set(
        Group.objects.get(name="Comptabilité").permissions.values_list("codename", flat=True)
    )
    assert {"add_settlementchannel", "change_settlementchannel", "view_paymentintent"} <= codenames
    assert "delete_settlementchannel" not in codenames


# --- Contraintes des intentions ----------------------------------------------------------------


@pytest.fixture
def saved(db):
    provider = VerifiedProviderFactory()
    channel = SettlementChannel.objects.create(
        slug="wave", gateway="manual_mobile_money", label_fr="Wave"
    )

    counter = iter(range(1_000))

    def make(**fields) -> PaymentIntent:
        data = {
            "purpose": "commission_settlement",
            "gateway": "manual_mobile_money",
            "origin": "pro_declared",
            "status": "declared",
            "declared_xof": 4_500,
            "reference": f"T_REF{next(counter):05d}",
            "channel": channel,
            "provider": provider,
            "declared_by": provider.owner,
            "payload_hash": "h",
            "idempotency_key": f"k-{next(counter)}",
        }
        return PaymentIntent.objects.create(**(data | fields))

    return make


def test_une_reference_ne_sert_qu_une_fois_par_canal(saved):
    first = saved(reference="T_SAME0001")
    with transaction.atomic(), pytest.raises(IntegrityError):
        saved(reference="T_SAME0001")
    # Rejetée, la référence se libère.
    PaymentIntent.objects.filter(pk=first.pk).update(status="rejected", reject_reason="not_found")
    saved(reference="T_SAME0001")


@pytest.mark.parametrize(
    "fields",
    [
        {"declared_xof": 0},
        {"payer_last4": "12a4"},
        {"payer_last4": "123"},
        {"status": "confirmed"},  # sans montant reçu ni décision
        {"received_xof": 4_500},  # reçu sans confirmation
        {"status": "rejected"},  # sans motif
        {"status": "needs_correction"},  # sans motif de correction
        {"reference": "", "receipt_number": ""},
    ],
)
def test_les_contraintes_des_intentions_tiennent_en_base(saved, fields):
    with transaction.atomic(), pytest.raises(IntegrityError):
        saved(**fields)


def test_une_intention_confirmee_porte_son_montant_recu(saved):
    confirmed = saved(status="confirmed", received_xof=4_400, decided_at=timezone.now())
    assert confirmed.received_xof == 4_400
