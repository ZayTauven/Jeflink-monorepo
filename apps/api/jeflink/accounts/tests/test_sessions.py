from datetime import timedelta

import jwt
import pytest
from django.utils import timezone

from jeflink.accounts.models import DeviceSession, Role
from jeflink.accounts.services import grant_role
from jeflink.accounts.sessions import (
    clean_device_label,
    clear_dormant_restriction,
    create_session,
    is_dormant_login,
    refresh_session,
    revoke_session,
    session_state,
)
from jeflink.accounts.tokens import decode_access, encode_access
from jeflink.common.errors import DomainError
from jeflink.trust.models import AuditEvent

durable_db = pytest.mark.django_db(transaction=True, databases="__all__", serialized_rollback=True)


def open_session(user, **kwargs):
    kwargs.setdefault("app", "client")
    kwargs.setdefault("platform", "android")
    return create_session(user=user, **kwargs)


def error_code(callable_, *args):
    with pytest.raises(DomainError) as exc:
        callable_(*args)
    return exc.value.code


# --- Jetons d'accès ----------------------------------------------------------------------


@pytest.mark.django_db
def test_access_porte_les_claims_attendus(user_factory, settings):
    user = user_factory()
    pair = open_session(user)
    claims = decode_access(pair.access)
    assert claims["sub"] == str(user.public_id)
    assert claims["sid"] == str(pair.session.public_id)
    assert claims["mfa"] is False
    assert claims["restricted"] is False
    assert "role" not in claims and "roles" not in claims
    assert jwt.get_unverified_header(pair.access)["kid"] == "t1"
    assert 0 < claims["exp"] - claims["iat"] <= 900


def _encode(**overrides):
    now = timezone.now()
    kwargs = {
        "user_public_id": "00000000-0000-0000-0000-000000000001",
        "session_public_id": "00000000-0000-0000-0000-000000000002",
        "app": "client",
        "auth_time": now,
        "mfa_at": None,
        "restricted": False,
        "issued_at": now,
        "expires_at": now + timedelta(minutes=15),
    }
    kwargs.update(overrides)
    return encode_access(**kwargs)


def test_ancienne_cle_de_rotation_acceptee(settings):
    token = _encode()
    settings.JWT_SIGNING_KEYS = {"t0": "nouvelle-cle-" + "z" * 30, **settings.JWT_SIGNING_KEYS}
    assert decode_access(token)["sub"]


@pytest.mark.parametrize(
    "falsifier",
    [
        lambda t: t[:-4] + "AAAA",  # signature altérée
        lambda t: jwt.encode({"sub": "x"}, "autre-cle-" + "y" * 30, "HS256", headers={"kid": "t1"}),
        lambda t: jwt.encode({"sub": "x"}, "k" * 40, "HS256", headers={"kid": "inconnu"}),
        lambda t: jwt.encode({"sub": "x"}, None, "none", headers={"kid": "t1"}),
        lambda t: "pas-un-jwt",
    ],
)
def test_jetons_falsifies_refuses(falsifier):
    assert error_code(decode_access, falsifier(_encode())) == "token_invalid"


def test_jeton_expire():
    token = _encode(expires_at=timezone.now() - timedelta(seconds=1))
    assert error_code(decode_access, token) == "token_expired"


# --- Rotation et grâce --------------------------------------------------------------------


@pytest.mark.django_db
def test_rotation_normale(user_factory):
    r1 = open_session(user_factory()).refresh
    r2 = refresh_session(r1).refresh
    r3 = refresh_session(r2).refresh
    assert len({r1, r2, r3}) == 3


@pytest.mark.django_db
def test_refresh_interrompu_puis_rejoue_dix_minutes_plus_tard(user_factory):
    """Critère d'acceptation : la réponse de rotation est perdue, le client rejoue R1 plus tard."""
    r1 = open_session(user_factory()).refresh
    refresh_session(r1)  # R2 émis mais jamais reçu par le client
    DeviceSession.objects.update(rotated_at=timezone.now() - timedelta(minutes=10))
    r3 = refresh_session(r1).refresh  # grâce
    assert refresh_session(r3).refresh  # et la suite fonctionne
    assert DeviceSession.objects.get().revoked_at is None


@durable_db
def test_grace_une_seule_fois(user_factory):
    r1 = open_session(user_factory()).refresh
    refresh_session(r1)
    refresh_session(r1)  # grâce consommée
    assert error_code(refresh_session, r1) == "session_revoked"
    assert DeviceSession.objects.get().revoked_reason == "reuse_detected"
    assert AuditEvent.objects.filter(action="accounts.session.refresh_reuse_detected").exists()


@durable_db
def test_grace_limitee_a_24_h(user_factory):
    r1 = open_session(user_factory()).refresh
    refresh_session(r1)
    DeviceSession.objects.update(rotated_at=timezone.now() - timedelta(hours=25))
    assert error_code(refresh_session, r1) == "session_revoked"


@durable_db
def test_vol_du_refresh_detecte_au_refresh_suivant_du_vrai_client(user_factory):
    """Un voleur utilise la grâce avec R1 ; le vrai client présente ensuite R2 : révocation."""
    r1 = open_session(user_factory()).refresh
    r2 = refresh_session(r1).refresh  # le vrai client détient R2
    r3 = refresh_session(r1).refresh  # le voleur, par la grâce
    assert error_code(refresh_session, r2) == "session_revoked"
    # La session est révoquée pour tout le monde, voleur compris.
    assert error_code(refresh_session, r3) == "session_revoked"


@durable_db
def test_refresh_ancien_de_deux_generations(user_factory):
    r1 = open_session(user_factory()).refresh
    r2 = refresh_session(r1).refresh
    refresh_session(r2)
    assert error_code(refresh_session, r1) == "session_revoked"


@pytest.mark.django_db
@pytest.mark.parametrize("valeur", ["", "inconnu", "jfr_inconnu"])
def test_refresh_inconnu(valeur):
    assert error_code(refresh_session, valeur) == "refresh_invalid"


@pytest.mark.django_db
def test_session_expiree_ou_compte_desactive(user_factory):
    user = user_factory()
    pair = open_session(user)
    DeviceSession.objects.update(idle_expires_at=timezone.now() - timedelta(seconds=1))
    assert error_code(refresh_session, pair.refresh) == "session_revoked"

    other = open_session(user_factory())
    type(user).objects.filter(pk=other.session.user_id).update(
        is_active=False, deactivation_reason="fraud"
    )
    assert error_code(refresh_session, other.refresh) == "session_revoked"


# --- Création, limites, révocation ----------------------------------------------------------


@pytest.mark.django_db
def test_dix_sessions_au_plus(user_factory, settings):
    settings.MAX_ACTIVE_SESSIONS = 3
    user = user_factory()
    first = open_session(user)
    for _ in range(3):
        open_session(user)
    first.session.refresh_from_db()
    assert first.session.revoked_reason == "limit"
    assert DeviceSession.objects.filter(user=user, revoked_at__isnull=True).count() == 3
    assert AuditEvent.objects.filter(action="accounts.session.evicted_limit").count() == 1


@pytest.mark.django_db
def test_meme_appareil_remplace_la_session(user_factory):
    user = user_factory()
    first = open_session(user, install_id="inst-00000001")
    open_session(user, install_id="inst-00000001")
    first.session.refresh_from_db()
    assert first.session.revoked_reason == "replaced"


@pytest.mark.django_db
def test_revocation_immediate_dans_le_cache(user_factory):
    pair = open_session(user_factory())
    assert session_state(pair.session.public_id) == "active"
    revoke_session(pair.session, reason="user_revoked")
    assert session_state(pair.session.public_id) is None


@pytest.mark.django_db
def test_politique_ops_sur_la_console(user_factory):
    user = user_factory()
    grant_role(user=user, role=Role.OPS, reason_code="t", operator="a", second_operator="b")
    pair = open_session(user, app="console", platform="web", mfa_verified_at=timezone.now())
    session = pair.session
    assert session.absolute_expires_at - session.created_at <= timedelta(hours=12, seconds=5)
    assert session.idle_expires_at - session.created_at <= timedelta(minutes=30, seconds=5)
    claims = decode_access(pair.access)
    assert claims["mfa"] is True
    assert claims["exp"] - claims["iat"] == 600


@pytest.mark.parametrize(
    ("saisie", "attendu"),
    [
        ("Samsung A05", "Samsung A05"),
        ("  Tecno​ Spark  ", "Tecno Spark"),
        ("Tel de Awa 77 123 45 67", ""),
        ("x" * 80, "x" * 60),
    ],
)
def test_libelle_d_appareil_nettoye(saisie, attendu):
    assert clean_device_label(saisie) == attendu


# --- Compte dormant ------------------------------------------------------------------------


@pytest.mark.django_db
def test_compte_dormant(user_factory):
    user = user_factory()
    type(user).objects.filter(pk=user.pk).update(created_at=timezone.now() - timedelta(days=200))
    user.refresh_from_db()
    open_session(user, install_id="ancien-telephone")
    DeviceSession.objects.update(last_seen_at=timezone.now() - timedelta(days=61))
    assert is_dormant_login(user=user, install_id="nouveau-telephone")
    assert not is_dormant_login(user=user, install_id="ancien-telephone")
    DeviceSession.objects.update(last_seen_at=timezone.now() - timedelta(days=59))
    assert not is_dormant_login(user=user, install_id="nouveau-telephone")


@pytest.mark.django_db
def test_compte_recent_jamais_dormant(user_factory):
    assert not is_dormant_login(user=user_factory(), install_id="x-00000000")


@pytest.mark.django_db
def test_levee_de_restriction_par_l_ops(user_factory):
    user, ops = user_factory(), user_factory()
    pair = open_session(user, restricted=True)
    assert session_state(pair.session.public_id) == "restricted"
    assert clear_dormant_restriction(user=user, actor=ops, reason_code="bookings_described") == 1
    assert session_state(pair.session.public_id) == "active"
    assert AuditEvent.objects.filter(action="accounts.dormant.cleared").count() == 1
