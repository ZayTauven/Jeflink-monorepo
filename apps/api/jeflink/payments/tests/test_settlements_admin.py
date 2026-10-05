"""Règlements dans l'admin et en concurrence (spec 005, tâche 5), en transaction réelle : le
second facteur compte ses échecs hors transaction, et les verrous se testent entre deux
connexions."""

import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest
from django.contrib.auth.models import Group
from django.db import connection, transaction
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from jeflink.accounts.admin_site import STEP_UP_KEY
from jeflink.accounts.models import User
from jeflink.accounts.tests.mfa_helpers import enroll
from jeflink.accounts.tests.test_admin_mfa import code_for
from jeflink.common.errors import DomainError
from jeflink.payments import services
from jeflink.payments.models import PaymentIntent, SettlementChannel
from jeflink.providers.tests.factories import VerifiedProviderFactory
from jeflink.trust.models import AuditEvent
from jeflink.wallet.models import LedgerTransaction
from jeflink.wallet.selectors import provider_balance

from .test_settlements import owe

pytestmark = pytest.mark.django_db(transaction=True, databases="__all__", serialized_rollback=True)

PASSWORD = "mot-de-passe-long-et-unique-42"


def staff(phone: str, group: str | None) -> User:
    user = User.objects.create_user(phone, is_staff=True)
    user.set_password(PASSWORD)
    user.save()
    if group:
        user.groups.add(Group.objects.get(name=group))
    return user


def login(user):
    totp = enroll(user)
    client = Client()
    response = client.post(
        reverse("admin:login"),
        {"username": user.phone, "password": PASSWORD, "otp_code": code_for(totp)},
        REMOTE_ADDR="10.9.0.1",
    )
    assert response.status_code == 302
    return client, totp


@pytest.fixture
def setup():
    with transaction.atomic():
        provider = VerifiedProviderFactory()
        wave = SettlementChannel.objects.create(
            slug="wave", gateway="manual_mobile_money", label_fr="Wave"
        )
        owe(provider, 9_000)
        intents = [
            services.declare_settlement(
                provider=provider,
                actor=provider.owner,
                channel=wave,
                amount_xof=4_500,
                reference=f"T_ADMIN{n:05d}",
                paid_at=timezone.now(),
                payer_last4="",
                idempotency_key=uuid.uuid4().hex,
            ).intent
            for n in range(2)
        ]
    return provider, wave, intents


def act(client, action, intents, **data):
    return client.post(
        reverse("admin:payments_paymentintent_changelist"),
        {"action": action, "_selected_action": [i.pk for i in intents], "apply": "1", **data},
    )


def test_confirmer_exige_un_code_frais_puis_ouvre_cinq_minutes(setup):
    provider, _, (first, second) = setup
    client, totp = login(staff("+221770000301", "Rapprochement"))

    # Sans code : la page revient avec l'erreur, rien n'est écrit.
    response = act(client, "confirm", [first], otp_code="")
    assert response.status_code == 200
    assert "Code invalide" in response.content.decode()
    assert PaymentIntent.objects.get(pk=first.pk).status == "declared"

    response = act(client, "confirm", [first], otp_code=code_for(totp, 1))
    assert response.status_code == 302
    assert PaymentIntent.objects.get(pk=first.pk).status == "confirmed"
    assert AuditEvent.objects.filter(action="accounts.admin.step_up").count() == 1

    # Dans la fenêtre : une deuxième décision passe sans code.
    act(client, "reject", [second], reason="not_found", note="")
    assert PaymentIntent.objects.get(pk=second.pk).status == "rejected"
    assert provider_balance(provider).due_xof == 4_500

    # Fenêtre échue : le code est redemandé.
    session = client.session
    session[STEP_UP_KEY] = {**session[STEP_UP_KEY], "at": session[STEP_UP_KEY]["at"] - 301}
    session.save()
    page = client.get(reverse("admin:payments_paymentintent_record_cash"))
    assert 'name="otp_code"' in page.content.decode()
    assert 'type="hidden" name="otp_code"' not in page.content.decode()


def test_l_ops_enregistre_des_especes_dans_l_admin(setup):
    provider, _, _ = setup
    cash = SettlementChannel.objects.create(slug="caisse", gateway="cash", label_fr="Bureau")
    client, totp = login(staff("+221770000302", "Rapprochement"))
    url = reverse("admin:payments_paymentintent_record_cash")
    page = client.get(url)
    assert page.status_code == 200

    response = client.post(
        url,
        {
            "provider": provider.pk,
            "channel": cash.pk,
            "amount_xof": 1_000,
            "receipt_number": "R-0001",
            "idempotency_key": uuid.uuid4().hex,
            "otp_code": code_for(totp, 1),
        },
    )
    assert response.status_code == 302
    intent = PaymentIntent.objects.get(gateway="cash")
    assert (intent.status, intent.origin, intent.declared_by.phone) == (
        "confirmed",
        "ops_recorded",
        "+221770000302",
    )


def test_hors_du_groupe_rapprochement_ni_action_ni_saisie(setup):
    _, _, (first, _) = setup
    client, totp = login(staff("+221770000303", "Comptabilité"))
    act(client, "confirm", [first], otp_code=code_for(totp, 1))
    assert PaymentIntent.objects.get(pk=first.pk).status == "declared"
    assert client.get(reverse("admin:payments_paymentintent_record_cash")).status_code == 403


def test_les_groupes_ont_les_droits_attendus():
    reconciliation = set(
        Group.objects.get(name="Rapprochement").permissions.values_list("codename", flat=True)
    )
    accounting = set(
        Group.objects.get(name="Comptabilité").permissions.values_list("codename", flat=True)
    )
    assert {"decide_paymentintent", "view_paymentintent", "view_ledgertransaction"} <= (
        reconciliation
    )
    assert "decide_paymentintent" not in accounting
    assert "add_commissionrate" not in reconciliation


# --- Concurrence -------------------------------------------------------------------------------


def _in_thread(fn):
    def run(arg):
        try:
            return fn(arg)
        except DomainError as exc:
            return exc.code
        finally:
            connection.close()

    return run


def test_deux_confirmations_simultanees_n_ecrivent_qu_un_reglement(setup):
    provider, _, (first, _) = setup
    ops = staff("+221770000304", None)

    @_in_thread
    def confirm(_):
        services.confirm_settlement(intent=first, operator=ops, received_xof=4_500)
        return "ok"

    with ThreadPoolExecutor(2) as pool:
        results = sorted(pool.map(confirm, [0, 1]))

    assert results == ["ok", "settlement_not_pending"]
    assert LedgerTransaction.objects.filter(kind="settlement").count() == 1
    assert provider_balance(provider).due_xof == 4_500


def test_deux_declarations_simultanees_de_la_meme_reference(setup, settings):
    settings.WALLET_SETTLEMENT_MAX_PENDING = 10  # la mise en place en a déjà deux
    provider, wave, _ = setup
    owe(provider, 2_000)

    @_in_thread
    def declare(n):
        services.declare_settlement(
            provider=provider,
            actor=provider.owner,
            channel=wave,
            amount_xof=1_000,
            reference="T_RACE00001",
            paid_at=timezone.now() - timedelta(minutes=1),
            payer_last4="",
            idempotency_key=f"race-key-{n}-{uuid.uuid4().hex}",
        )
        return "ok"

    with ThreadPoolExecutor(2) as pool:
        results = sorted(pool.map(declare, [0, 1]))

    assert results == ["ok", "settlement_reference_used"]
    assert PaymentIntent.objects.filter(reference="T_RACE00001").count() == 1
