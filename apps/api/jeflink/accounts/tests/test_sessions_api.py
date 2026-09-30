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
    pair = open_session(user_factory(is_staff=True))
    response = bearer(api_client, pair).get(reverse("me-sessions"))
    assert response.status_code == 401
    assert response.json() == {"code": "account_disabled"}


def test_session_cookie_django_ignoree(client, user_factory):
    """L'API n'accepte que le Bearer : une session Django (admin) n'authentifie rien."""
    user = user_factory()
    client.force_login(user)
    assert client.get(reverse("me-sessions")).status_code == 401
