"""Tâche 11 : profil (``GET``/``PATCH /api/me/``), passage d'invité à complet."""

import pytest
from django.urls import reverse
from rest_framework.response import Response
from rest_framework.test import APIRequestFactory
from rest_framework.views import APIView

from jeflink.accounts.models import Role, User
from jeflink.accounts.permissions import RequiresCompleteProfile
from jeflink.accounts.services import grant_role, update_profile
from jeflink.accounts.sessions import create_session
from jeflink.common.errors import DomainError

pytestmark = pytest.mark.django_db


def bearer(api_client, user, **kwargs):
    pair = create_session(user=user, app="client", platform="android", **kwargs)
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {pair.access}")
    return api_client, pair


# --- Service ---------------------------------------------------------------------------------


def test_le_nom_fait_passer_l_invite_a_complet(user_factory):
    user = update_profile(user=user_factory(), display_name="  Awa   Diop ")
    user.refresh_from_db()
    assert user.display_name == "Awa Diop"
    assert user.profile_status == User.ProfileStatus.COMPLETE


@pytest.mark.parametrize(
    ("name", "code"),
    [
        ("", "display_name_length"),
        ("A", "display_name_length"),
        ("x" * 81, "display_name_length"),
        ("Awa‮Diop", "display_name_invalid"),
        ("Support Jeflink", "display_name_reserved"),
        ("Awa www.exemple.sn", "display_name_reserved"),
        ("Awa 77 123 45 67", "display_name_reserved"),
    ],
)
def test_nom_refuse_profil_intact(complete_user_factory, name, code):
    user = complete_user_factory(display_name="Awa")
    with pytest.raises(DomainError) as exc:
        update_profile(user=user, display_name=name)
    assert exc.value.code == code
    user.refresh_from_db()
    assert (user.display_name, user.profile_status) == ("Awa", User.ProfileStatus.COMPLETE)


def test_e_mail_normalise_puis_efface(user_factory):
    user = update_profile(user=user_factory(), email=" awa@Exemple.SN ")
    assert user.email == "awa@exemple.sn"
    assert update_profile(user=user, email="").email == ""


def test_langue(user_factory):
    assert update_profile(user=user_factory(), preferred_language="wo").preferred_language == "wo"
    with pytest.raises(DomainError) as exc:
        update_profile(user=user_factory(), preferred_language="en")
    assert exc.value.code == "language_invalid"


def test_rien_a_changer_rien_n_est_ecrit(complete_user_factory):
    user = complete_user_factory()
    before = user.updated_at
    update_profile(user=user)
    user.refresh_from_db()
    assert user.updated_at == before


def test_compte_desactive_entre_temps(user_factory):
    user = user_factory()
    User.objects.filter(pk=user.pk).update(is_active=False, deactivation_reason="ops_other")
    with pytest.raises(DomainError) as exc:
        update_profile(user=user, display_name="Awa")
    assert exc.value.code == "account_disabled"


# --- API -------------------------------------------------------------------------------------


def test_get_me(api_client, complete_user_factory):
    user = complete_user_factory(phone="+221771234567", display_name="Awa", email="a@b.sn")
    grant_role(user=user, role=Role.OWNER, reason_code="test")
    client, _ = bearer(api_client, user)
    response = client.get(reverse("me"))
    assert response.status_code == 200
    body = response.json()
    assert body == {
        "public_id": str(user.public_id),
        "phone": "+221771234567",
        "phone_display": "77 123 45 67",
        "display_name": "Awa",
        "email": "a@b.sn",
        "preferred_language": "fr",
        "profile_status": "complete",
        "roles": ["owner"],
        "created_at": body["created_at"],
        "restricted": False,
        "restriction_kind": None,
    }
    assert body["created_at"]


def test_get_me_sans_jeton(api_client):
    response = api_client.get(reverse("me"))
    assert response.status_code == 401
    assert response.json() == {"code": "not_authenticated"}


class _AcceptQuoteView(APIView):
    """Action factice qui exige un profil complet (accepter un devis, Q5)."""

    permission_classes = [RequiresCompleteProfile]

    def post(self, request):
        return Response({"ok": True})


def test_invite_refuse_puis_accepte_apres_patch(api_client, user_factory):
    """Critère : un invité reçoit 403 profile_incomplete, puis l'action passe après PATCH."""
    user = user_factory()
    client, pair = bearer(api_client, user)
    factory = APIRequestFactory()
    action = _AcceptQuoteView.as_view()

    def rejouer():
        return action(factory.post("/", HTTP_AUTHORIZATION=f"Bearer {pair.access}"))

    refus = rejouer()
    assert refus.status_code == 403
    assert refus.data == {"code": "profile_incomplete"}

    response = client.patch(reverse("me"), {"display_name": "Awa"}, format="json")
    assert response.status_code == 200
    assert response.json()["profile_status"] == "complete"
    # Même jeton : le statut du profil est relu en base, pas porté par le JWT.
    assert rejouer().status_code == 200


def test_patch_ne_touche_ni_au_numero_ni_au_statut(api_client, user_factory):
    user = user_factory(phone="+221771234567")
    client, _ = bearer(api_client, user)
    response = client.patch(
        reverse("me"),
        {
            "phone": "+221779999999",
            "profile_status": "complete",
            "roles": ["ops"],
            "preferred_language": "wo",
        },
        format="json",
    )
    assert response.status_code == 200
    user.refresh_from_db()
    assert user.phone == "+221771234567"
    assert user.profile_status == User.ProfileStatus.GUEST
    assert user.preferred_language == "wo"
    assert not user.role_grants.exists()


def test_patch_nom_refuse_sans_echo(api_client, user_factory):
    client, _ = bearer(api_client, user_factory())
    response = client.patch(reverse("me"), {"display_name": "Ops Jeflink"}, format="json")
    assert response.status_code == 400
    assert response.json() == {"code": "display_name_reserved"}


def test_patch_e_mail_invalide(api_client, user_factory):
    client, _ = bearer(api_client, user_factory())
    response = client.patch(reverse("me"), {"email": "pas-un-mail"}, format="json")
    assert response.status_code == 400
    assert response.json() == {"code": "invalid", "fields": {"email": ["invalid"]}}


def test_patch_langue_inconnue(api_client, user_factory):
    client, _ = bearer(api_client, user_factory())
    response = client.patch(reverse("me"), {"preferred_language": "en"}, format="json")
    assert response.status_code == 400
    assert response.json() == {
        "code": "invalid",
        "fields": {"preferred_language": ["invalid_choice"]},
    }


# --- Session restreinte (compte dormant, S18) ------------------------------------------------


@pytest.mark.parametrize(("role", "kind"), [(None, "client"), (Role.TECHNICIAN, "pro")])
def test_session_restreinte_lit_un_profil_minimal(api_client, complete_user_factory, role, kind):
    user = complete_user_factory(phone="+221771234567", display_name="Ancien", email="x@y.sn")
    if role:
        grant_role(user=user, role=role, reason_code="test")
    client, _ = bearer(api_client, user, restricted=True)
    response = client.get(reverse("me"))
    assert response.status_code == 200
    body = response.json()
    # Rien de l'ancien titulaire : seul le numéro, que la session vient de prouver (I2).
    assert body == {
        "public_id": str(user.public_id),
        "phone": "+221771234567",
        "phone_display": "77 123 45 67",
        "display_name": "",
        "email": "",
        "preferred_language": "fr",
        "profile_status": "guest",
        "roles": [],
        "created_at": None,
        "restricted": True,
        "restriction_kind": kind,
    }


def test_session_restreinte_ne_modifie_pas_le_profil(api_client, complete_user_factory):
    user = complete_user_factory(display_name="Ancien")
    client, _ = bearer(api_client, user, restricted=True)
    response = client.patch(reverse("me"), {"display_name": "Nouveau"}, format="json")
    assert response.status_code == 403
    assert response.json() == {"code": "session_restricted"}
    user.refresh_from_db()
    assert user.display_name == "Ancien"
