"""Tâche 15 : endpoints Ops sur les comptes (tag ops-accounts ; S14, S25, S30)."""

from datetime import timedelta

import pytest
from django.contrib.auth.models import Group
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from jeflink.accounts.models import DeviceSession, Role
from jeflink.accounts.otp_limits import block_phone, phone_blocked_until
from jeflink.accounts.services import grant_role
from jeflink.accounts.sessions import create_session
from jeflink.common.pii import phone_hmac
from jeflink.trust.models import AuditEvent

from .mfa_helpers import enroll

pytestmark = pytest.mark.django_db(transaction=True, databases="__all__", serialized_rollback=True)

PHONE = "+221771234567"


def make_ops(user_factory, group="Support"):
    user = user_factory()
    grant_role(user=user, role=Role.OPS, reason_code="t", operator="a", second_operator="b")
    user.groups.add(Group.objects.get(name=group))
    enroll(user)
    return user


def console(user, *, mfa_age=timedelta(0)):
    pair = create_session(
        user=user, app="console", platform="web", mfa_verified_at=timezone.now() - mfa_age
    )
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {pair.access}")
    return client


@pytest.fixture
def agent(user_factory):
    return make_ops(user_factory)


@pytest.fixture
def awa(complete_user_factory):
    return complete_user_factory(phone=PHONE, display_name="Awa Diop")


def act(client, slug, target, reason, note=""):
    return client.post(
        reverse(f"ops-{slug}", args=[target.public_id]),
        {"reason_code": reason, "note": note},
        format="json",
    )


# --- Recherche et fiche ---------------------------------------------------------------------------


def test_recherche_par_numero_en_post(agent, awa):
    response = console(agent).post(reverse("ops-search"), {"phone": "77 123 45 67"}, format="json")
    assert response.status_code == 200
    [result] = response.json()["results"]
    assert result["public_id"] == str(awa.public_id)
    assert result["phone_masked"] == "+221 •••••••67"
    assert "123 45" not in response.content.decode()
    event = AuditEvent.objects.get(action="ops.accounts.searched")
    assert event.metadata == {"phone_hmac": phone_hmac(PHONE), "found": True}


def test_recherche_sans_resultat_et_comptes_ops_invisibles(agent, user_factory):
    other_ops = make_ops(user_factory)
    client = console(agent)
    for phone in ("+221770000000", other_ops.phone, agent.phone):
        response = client.post(reverse("ops-search"), {"phone": phone}, format="json")
        assert response.json() == {"results": []}


def test_recherche_numero_invalide(agent):
    response = console(agent).post(reverse("ops-search"), {"phone": "12"}, format="json")
    assert response.status_code == 400
    assert response.json() == {"code": "phone_invalid"}


def test_fiche_du_compte(agent, awa):
    create_session(user=awa, app="client", platform="android", device_label="Samsung A05")
    block_phone(PHONE)
    response = console(agent).get(reverse("ops-account", args=[awa.public_id]))
    assert response.status_code == 200
    body = response.json()
    assert body["phone_masked"] == "+221 •••••••67"
    assert PHONE not in response.content.decode()
    assert [s["device_label"] for s in body["sessions"]] == ["Samsung A05"]
    assert body["otp_blocked_until"] is not None
    assert body["deleted"] is False and body["dormant_restricted"] is False


@pytest.mark.parametrize("cible", ["soi", "ops", "staff"])
def test_cible_interdite(agent, user_factory, cible):
    target = {
        "soi": lambda: agent,
        "ops": lambda: make_ops(user_factory),
        "staff": lambda: user_factory(is_staff=True),
    }[cible]()
    client = console(agent)
    assert client.get(reverse("ops-account", args=[target.public_id])).json() == {
        "code": "ops_target_forbidden"
    }
    assert act(client, "deactivate", target, "fraud").json() == {"code": "ops_target_forbidden"}


def test_compte_inconnu_404(agent):
    import uuid

    response = console(agent).get(reverse("ops-account", args=[uuid.uuid4()]))
    assert response.status_code == 404


def test_sans_second_facteur_aucune_permission(agent, awa):
    """Un compte ops connecté hors console (mfa=false) n'a aucun pouvoir Ops."""
    pair = create_session(user=agent, app="client", platform="android")
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {pair.access}")
    response = client.get(reverse("ops-account", args=[awa.public_id]))
    assert response.status_code == 403
    assert response.json() == {"code": "ops_forbidden"}


# --- Révélation du numéro ------------------------------------------------------------------------


def test_reveler_le_numero(agent, awa):
    response = act(console(agent), "reveal-phone", awa, "support_call", "Appel entrant")
    assert response.status_code == 200
    assert response.json() == {"phone": PHONE}
    event = AuditEvent.objects.get(action="ops.accounts.phone_revealed")
    assert event.metadata == {"reason_code": "support_call", "note": "Appel entrant"}
    assert event.actor == agent


@pytest.mark.parametrize(
    ("reason", "note", "code"),
    [
        ("curiosite", "", "invalid"),
        ("support_call", "rappeler au 77 123 45 67", "note_invalid"),
        ("support_call", "x" * 281, "note_invalid"),
    ],
)
def test_motif_et_note_controles(agent, awa, reason, note, code):
    response = act(console(agent), "reveal-phone", awa, reason, note)
    assert response.status_code == 400
    assert response.json()["code"] == code
    assert "77 123" not in response.content.decode()
    assert not AuditEvent.objects.filter(action="ops.accounts.phone_revealed").exists()


# --- Actions « manage » (step-up, S25) -----------------------------------------------------------


def test_revoquer_les_sessions(agent, awa):
    victim = create_session(user=awa, app="client", platform="android")
    response = act(console(agent), "revoke-sessions", awa, "device_lost")
    assert response.status_code == 204
    victim.session.refresh_from_db()
    assert victim.session.revoked_reason == "ops_revoked"
    event = AuditEvent.objects.get(action="ops.accounts.sessions_revoked")
    assert event.metadata == {"reason_code": "device_lost", "count": 1}


def test_manage_exige_un_totp_recent(agent, awa):
    client = console(agent, mfa_age=timedelta(minutes=10))
    response = act(client, "revoke-sessions", awa, "device_lost")
    assert response.status_code == 403
    assert response.json() == {"code": "ops_step_up_required"}


def test_groupe_sans_manage_refuse(user_factory, awa):
    finance = make_ops(user_factory, group="Finance")
    response = act(console(finance), "revoke-sessions", awa, "device_lost")
    assert response.json() == {"code": "ops_forbidden"}


def test_lever_le_blocage_otp(agent, awa):
    block_phone(PHONE)
    assert phone_blocked_until(PHONE) is not None
    assert act(console(agent), "unblock-otp", awa, "user_verified").status_code == 204
    assert phone_blocked_until(PHONE) is None
    assert AuditEvent.objects.filter(action="ops.accounts.otp_unblocked").count() == 1


def test_desactivation_pour_fraude_puis_reactivation_par_un_autre_ops(agent, awa, user_factory):
    """S30 : l'Ops qui a désactivé pour fraude ne peut pas réactiver lui-même."""
    victim = create_session(user=awa, app="client", platform="android")
    client = console(agent)
    assert act(client, "deactivate", awa, "fraud").status_code == 204
    awa.refresh_from_db()
    assert (awa.is_active, awa.deactivation_reason, awa.deactivated_by) == (False, "fraud", agent)
    victim.session.refresh_from_db()
    assert victim.session.revoked_reason == "account_disabled"

    response = act(client, "reactivate", awa, "user_verified")
    assert response.status_code == 403
    assert response.json() == {"code": "ops_second_operator_required"}

    other = make_ops(user_factory)
    assert act(console(other), "reactivate", awa, "user_verified").status_code == 204
    awa.refresh_from_db()
    assert awa.is_active and awa.deactivation_reason == ""
    event = AuditEvent.objects.get(action="accounts.user.reactivated")
    assert event.metadata["previous_reason"] == "fraud"


def test_desactivation_hors_fraude_reactivable_par_le_meme_ops(agent, awa):
    client = console(agent)
    assert act(client, "deactivate", awa, "ops_other").status_code == 204
    assert act(client, "reactivate", awa, "error_correction").status_code == 204


def test_compte_desactive_refuse_immediatement(agent, awa):
    victim = APIClient()
    pair = create_session(user=awa, app="client", platform="android")
    victim.credentials(HTTP_AUTHORIZATION=f"Bearer {pair.access}")
    act(console(agent), "deactivate", awa, "fraud")
    assert victim.get(reverse("me")).status_code == 401


def test_lever_la_restriction_du_compte_dormant(agent, awa):
    """S18 : « C'est bien mon compte », vérifié par le support."""
    restricted = create_session(user=awa, app="client", platform="android", restricted=True)
    assert act(console(agent), "clear-dormant", awa, "owner_verified").status_code == 204
    awa.refresh_from_db()
    assert awa.dormant_restricted_since is None
    session = DeviceSession.objects.get(pk=restricted.session.pk)
    assert session.restricted is False
    assert AuditEvent.objects.filter(action="accounts.dormant.cleared").count() == 1


def test_aucune_donnee_personnelle_dans_les_urls():
    """S14 : aucune route ops ne prend de numéro en paramètre."""
    from django.urls import URLPattern, URLResolver, get_resolver

    def walk(patterns, prefix=""):
        for pattern in patterns:
            if isinstance(pattern, URLResolver):
                yield from walk(pattern.url_patterns, prefix + str(pattern.pattern))
            elif isinstance(pattern, URLPattern):
                yield prefix + str(pattern.pattern)

    ops_routes = [r for r in walk(get_resolver().url_patterns) if "ops/" in r]
    assert len(ops_routes) == 8
    assert all("<" not in r or "<uuid:public_id>" in r for r in ops_routes)
    assert not [r for r in ops_routes if "phone>" in r or "<str:" in r]
