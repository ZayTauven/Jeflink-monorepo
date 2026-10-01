import pytest
from django.urls import reverse

from jeflink.accounts.models import DeviceSession
from jeflink.accounts.sessions import create_session

pytestmark = pytest.mark.django_db


def open_session(user, **kwargs):
    kwargs.setdefault("app", "client")
    kwargs.setdefault("platform", "android")
    return create_session(user=user, **kwargs)


def bearer(api_client, pair):
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {pair.access}")
    return api_client


def test_sans_jeton_401(api_client):
    response = api_client.get(reverse("me-sessions"))
    assert response.status_code == 401
    assert response.json() == {"code": "not_authenticated"}
    assert response["WWW-Authenticate"].startswith("Bearer")


def test_jeton_invalide_401(api_client):
    api_client.credentials(HTTP_AUTHORIZATION="Bearer abc.def.ghi")
    response = api_client.get(reverse("me-sessions"))
    assert response.status_code == 401
    assert response.json() == {"code": "token_invalid"}


def test_refresh_endpoint(api_client, user_factory):
    pair = open_session(user_factory())
    response = api_client.post(
        reverse("auth-token-refresh"), {"refresh": pair.refresh}, format="json"
    )
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"access", "refresh", "access_expires_at"}
    assert body["refresh"] != pair.refresh


def test_refresh_invalide(api_client):
    response = api_client.post(reverse("auth-token-refresh"), {"refresh": "jfr_x"}, format="json")
    assert response.status_code == 401
    assert response.json() == {"code": "refresh_invalid"}


def test_logout_coupe_l_acces_immediatement(api_client, user_factory):
    pair = open_session(user_factory())
    client = bearer(api_client, pair)
    assert client.post(reverse("auth-logout")).status_code == 204
    response = client.get(reverse("me-sessions"))
    assert response.status_code == 401
    assert response.json() == {"code": "session_revoked"}
    assert DeviceSession.objects.get().revoked_reason == "logout"


def test_liste_de_mes_sessions(api_client, user_factory):
    user = user_factory()
    current = open_session(user, device_label="Samsung A05")
    open_session(user, app="web", platform="web")
    open_session(user_factory())  # session d'un autre compte : jamais listée
    results = bearer(api_client, current).get(reverse("me-sessions")).json()["results"]
    assert len(results) == 2
    assert [s["is_current"] for s in results].count(True) == 1
    assert {"install_id", "refresh_hash"}.isdisjoint(results[0])


def test_revoquer_une_de_mes_sessions(api_client, user_factory):
    user = user_factory()
    current, other = open_session(user), open_session(user, app="web", platform="web")
    url = reverse("me-session-detail", args=[other.session.public_id])
    assert bearer(api_client, current).delete(url).status_code == 204
    other.session.refresh_from_db()
    assert other.session.revoked_reason == "user_revoked"


def test_session_d_un_autre_404(api_client, user_factory):
    mine, theirs = open_session(user_factory()), open_session(user_factory())
    url = reverse("me-session-detail", args=[theirs.session.public_id])
    response = bearer(api_client, mine).delete(url)
    assert response.status_code == 404
    assert response.json() == {"code": "not_found"}
    theirs.session.refresh_from_db()
    assert theirs.session.revoked_at is None


def test_deconnecter_les_autres_appareils(api_client, user_factory):
    user = user_factory()
    current = open_session(user)
    others = [open_session(user, app="web", platform="web"), open_session(user, app="pro")]
    assert bearer(api_client, current).post(reverse("me-sessions-revoke-others")).status_code == 204
    assert all(DeviceSession.objects.get(pk=o.session.pk).revoked_at for o in others)
    assert DeviceSession.objects.get(pk=current.session.pk).revoked_at is None


def test_session_restreinte_sans_donnees_personnelles(api_client, user_factory):
    pair = open_session(user_factory(), restricted=True)
    response = bearer(api_client, pair).get(reverse("me-sessions"))
    assert response.status_code == 403
    assert response.json() == {"code": "session_restricted"}
    # La déconnexion reste permise.
    assert bearer(api_client, pair).post(reverse("auth-logout")).status_code == 204


def test_compte_technique_refuse(api_client, user_factory):
    """Un compte promu technique après sa connexion perd l'accès API (S3)."""
    user = user_factory()
    pair = open_session(user)
    type(user).objects.filter(pk=user.pk).update(is_staff=True)
    response = bearer(api_client, pair).get(reverse("me-sessions"))
    assert response.status_code == 401
    assert response.json() == {"code": "account_disabled"}


def test_session_cookie_django_ignoree(client, user_factory):
    """L'API n'accepte que le Bearer : une session Django (admin) n'authentifie rien."""
    user = user_factory()
    client.force_login(user)
    assert client.get(reverse("me-sessions")).status_code == 401


def test_session_d_un_autre_sujet_refusee(api_client, user_factory):
    """M2 : un jeton dont le sid appartient à un autre compte est refusé."""
    from datetime import timedelta

    from django.utils import timezone

    from jeflink.accounts.tokens import encode_access

    victim, other = open_session(user_factory()), user_factory()
    now = timezone.now()
    forged = encode_access(
        user_public_id=other.public_id,
        session_public_id=victim.session.public_id,
        app="client",
        auth_time=now,
        mfa_at=None,
        restricted=False,
        issued_at=now,
        expires_at=now + timedelta(minutes=5),
    )
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {forged}")
    response = api_client.get(reverse("me-sessions"))
    assert response.status_code == 401
    assert response.json() == {"code": "token_invalid"}


def test_reponses_non_mises_en_cache(api_client, user_factory):
    """M5 : ni les jetons ni les données authentifiées ne sont mis en cache."""
    pair = open_session(user_factory())
    refresh = api_client.post(
        reverse("auth-token-refresh"), {"refresh": pair.refresh}, format="json"
    )
    assert refresh["Cache-Control"] == "private, no-store"
    listing = bearer(api_client, pair).get(reverse("me-sessions"))
    assert listing["Cache-Control"] == "private, no-store"
    assert "Authorization" in listing["Vary"]


def test_compte_ops_depuis_l_app_client_sans_permission_ops(user_factory):
    """Critère d'acceptation : un compte ops connecté depuis l'app client n'a aucun droit Ops."""
    from django.contrib.auth.models import Group
    from rest_framework.request import Request
    from rest_framework.test import APIRequestFactory

    from jeflink.accounts.models import Role
    from jeflink.accounts.permissions import HasOpsPerm
    from jeflink.accounts.services import grant_role
    from jeflink.accounts.tokens import decode_access

    user = user_factory()
    grant_role(user=user, role=Role.OPS, reason_code="t", operator="a", second_operator="b")
    user.groups.add(Group.objects.get(name="Admin"))
    pair = open_session(user, app="client")
    request = Request(APIRequestFactory().get("/"))
    request.user, request.auth = user, decode_access(pair.access)
    assert request.auth["mfa"] is False
    assert not HasOpsPerm("ops.accounts.view", step_up=False)().has_permission(request, None)


def test_revocation_par_le_refresh_sans_acces_valide(api_client, user_factory):
    """Revue BFF, I5 : la déconnexion web révoque la session même après expiration de l'accès."""
    pair = open_session(user_factory())
    response = api_client.post(
        reverse("auth-token-revoke"), {"refresh": pair.refresh}, format="json"
    )
    assert response.status_code == 204
    pair.session.refresh_from_db()
    assert pair.session.revoked_reason == "logout"
    refused = api_client.post(
        reverse("auth-token-refresh"), {"refresh": pair.refresh}, format="json"
    )
    assert refused.status_code == 401


def test_revocation_par_refresh_inconnu_meme_reponse(api_client):
    for refresh in ("jfr_inconnu", "pas-un-refresh", ""):
        response = api_client.post(
            reverse("auth-token-revoke"), {"refresh": refresh}, format="json"
        )
        assert response.status_code == 204
