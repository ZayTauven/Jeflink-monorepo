import threading
from datetime import timedelta

import pytest
from django.db import connections
from django.urls import reverse
from django.utils import timezone

from jeflink.accounts.models import DeviceSession, OtpChallenge, OtpDelivery, Role, User
from jeflink.accounts.otp import hash_code
from jeflink.accounts.services import grant_role
from jeflink.notifications.sms.fake import FakeSmsGateway
from jeflink.trust.models import AuditEvent

from .otp_helpers import (
    INSTALL_A,
    INSTALL_B,
    PHONE,
    last_code,
    other_code,
    request_code,
    verify,
)

durable_db = pytest.mark.django_db(transaction=True, databases="__all__", serialized_rollback=True)


@pytest.fixture
def ask(api_client, django_capture_on_commit_callbacks):
    """Demande un code et exécute l'envoi (Celery en mode EAGER, déclenché au commit)."""

    def _ask(phone=PHONE, **kwargs):
        with django_capture_on_commit_callbacks(execute=True):
            response = request_code(api_client, phone, **kwargs)
        return response

    return _ask


@pytest.fixture
def check(api_client, django_capture_on_commit_callbacks):
    def _check(challenge, code, **kwargs):
        with django_capture_on_commit_callbacks(execute=True):
            return verify(api_client, challenge, code, **kwargs)

    return _check


# --- Demande ---------------------------------------------------------------------------------


@pytest.mark.django_db
def test_demande_envoie_un_sms_et_ne_stocke_ni_code_ni_secret(ask):
    response = ask()
    assert response.status_code == 202
    body = response.json()
    assert set(body) == {
        "challenge_id",
        "challenge_secret",
        "phone_display",
        "code_length",
        "expires_at",
        "resend_available_at",
        "deliveries_remaining",
    }
    assert body["phone_display"] == "77 123 45 67"
    assert body["deliveries_remaining"] == 2
    code = last_code()
    challenge = OtpChallenge.objects.get()
    delivery = OtpDelivery.objects.get()
    assert delivery.status == "sent"
    assert body["challenge_secret"] not in challenge.challenge_secret_hash
    assert delivery.code_hash == hash_code(delivery.public_id, code)
    assert code not in str(OtpDelivery.objects.values().get())
    assert not User.objects.exists()  # compte créé seulement après vérification


@pytest.mark.django_db
def test_meme_cle_meme_reponse_sans_second_sms(ask):
    first = ask(key="cle-idempotence-0001-abcdefgh").json()
    second = ask(key="cle-idempotence-0001-abcdefgh").json()
    assert first == second
    assert len(FakeSmsGateway.outbox) == 1
    assert OtpChallenge.objects.count() == 1
    ask(key="cle-idempotence-0002-abcdefgh")
    assert OtpChallenge.objects.count() == 2


@pytest.mark.django_db
def test_reponse_identique_compte_existant_ou_non(ask, user_factory):
    """Anti-énumération : même forme de réponse, que le numéro ait un compte ou non."""
    user_factory(phone="+221771234568")
    existing = ask(phone="+221771234568").json()
    unknown = ask(phone="+221771234569").json()
    assert set(existing) == set(unknown)
    assert existing["deliveries_remaining"] == unknown["deliveries_remaining"]


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("phone", "code"),
    [
        ("+33 6 12 34 56 78", "phone_region_not_supported"),
        ("12", "phone_invalid"),
        ("+33 1 42 68 53 00", "phone_not_mobile"),
    ],
)
def test_numeros_refuses_sans_echo(ask, phone, code):
    response = ask(phone=phone)
    assert response.status_code == 400
    assert response.json() == {"code": code}
    assert not OtpChallenge.objects.exists()


@pytest.mark.django_db
def test_cle_d_idempotence_obligatoire(api_client):
    response = api_client.post(
        reverse("auth-otp-request"), {"phone": PHONE, "app": "client"}, format="json"
    )
    assert response.json() == {"code": "idempotency_key_required"}


@pytest.mark.django_db
def test_web_et_console_reserves_au_bff(api_client, ask):
    assert ask(app="web").json()["code"] == "invalid"
    response = api_client.post(
        reverse("auth-otp-request"),
        {"phone": PHONE},
        format="json",
        HTTP_IDEMPOTENCY_KEY="cle-idempotence-0003-abcdefgh",
    )
    assert response.json() == {"code": "app_invalid"}


@pytest.mark.django_db
def test_web_via_le_bff_de_confiance(ask, settings):
    settings.ALLOWED_HOSTS = ["api", "testserver"]
    response = ask(
        app=None,
        HTTP_HOST="api",
        HTTP_X_JEFLINK_BFF=settings.BFF_SHARED_SECRETS[0],
        HTTP_X_JEFLINK_APP="web",
        HTTP_X_JEFLINK_CLIENT_IP="41.82.1.2",
    )
    assert response.status_code == 202
    assert OtpChallenge.objects.get().app == "web"
    assert FakeSmsGateway.outbox[-1].body.endswith(f"#{last_code()}")


@pytest.mark.django_db
def test_sixieme_demande_de_l_heure_refusee(ask):
    for _ in range(5):
        assert ask().status_code == 202
    response = ask()
    assert response.status_code == 429
    assert response.json()["code"] == "otp_rate_limited"


@pytest.mark.django_db
def test_le_code_ne_transite_jamais_par_le_broker(
    api_client, monkeypatch, django_capture_on_commit_callbacks
):
    """S28 : la tâche ne reçoit que l'identifiant d'envoi."""
    from jeflink.accounts import tasks

    calls = []
    monkeypatch.setattr(tasks.send_otp, "delay", lambda *a, **kw: calls.append((a, kw)))
    monkeypatch.setattr(
        tasks.send_otp, "apply_async", lambda *a, **kw: calls.append(("apply_async", a, kw))
    )
    with django_capture_on_commit_callbacks(execute=True):
        request_code(api_client)
    assert calls == [((str(OtpDelivery.objects.get().public_id),), {})]


# --- Vérification ------------------------------------------------------------------------------


@pytest.mark.django_db
def test_premiere_connexion_cree_un_compte_invite(ask, check, api_client):
    challenge = ask().json()
    response = check(challenge, last_code())
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "authenticated"
    assert body["is_new_user"] is True
    assert body["restricted"] is False
    assert body["user"]["profile_status"] == "guest"
    assert body["user"]["roles"] == []
    user = User.objects.get()
    assert user.phone == PHONE and user.terms_version and user.phone_verified_at
    assert OtpChallenge.objects.get().status == "verified"
    # Les jetons fonctionnent.
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {body['tokens']['access']}")
    assert api_client.get(reverse("me-sessions")).status_code == 200
    actions = set(AuditEvent.objects.values_list("action", flat=True))
    assert {"accounts.user.created", "accounts.otp.verified"} <= actions


@pytest.mark.django_db
def test_compte_existant_et_autres_appareils(ask, check, user_factory):
    from jeflink.accounts.sessions import create_session

    user = user_factory(phone=PHONE)
    create_session(user=user, app="web", platform="web", device_label="Chrome")
    challenge = ask().json()
    body = check(challenge, last_code()).json()
    assert body["is_new_user"] is False
    assert [s["device_label"] for s in body["other_sessions"]] == ["Chrome"]


@pytest.mark.django_db
def test_mauvais_code(ask, check):
    challenge = ask().json()
    response = check(challenge, other_code(last_code()))
    assert response.status_code == 400
    assert response.json() == {"code": "otp_invalid", "attempts_remaining": 4}
    assert not User.objects.exists()


@durable_db
def test_cinq_echecs_verrouillent(ask, check):
    challenge = ask().json()
    code = last_code()
    for _ in range(4):
        check(challenge, other_code(code))
    locked = check(challenge, other_code(code))
    assert locked.status_code == 429 and locked.json() == {"code": "otp_locked"}
    # Même le bon code est refusé ensuite.
    assert check(challenge, code).json() == {"code": "otp_locked"}
    assert AuditEvent.objects.filter(action="accounts.otp.locked").count() == 1


@pytest.mark.django_db
def test_ordre_des_controles(ask, check, user_factory):
    """S11 : conditions, puis challenge, puis code ; rien ne dépend du compte avant le code."""
    challenge = ask().json()
    assert check(challenge, last_code(), terms="ancienne").json() == {"code": "terms_not_accepted"}
    faux = {**challenge, "challenge_secret": "x" * 43}
    assert check(faux, last_code()).json() == {"code": "otp_challenge_invalid"}
    # Même erreur de code, que le numéro ait un compte ou non.
    user_factory(phone="+221771234568")
    avec = ask(phone="+221771234568").json()
    sans = ask(phone="+221771234569").json()
    assert check(avec, "000000").json()["code"] == check(sans, "000000").json()["code"]


@pytest.mark.django_db
def test_challenge_expire(ask, check):
    challenge = ask().json()
    OtpChallenge.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
    assert check(challenge, last_code()).json() == {"code": "otp_expired"}


@pytest.mark.django_db
def test_code_expire(ask, check):
    challenge = ask().json()
    OtpDelivery.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
    assert check(challenge, last_code()).json() == {"code": "otp_expired"}


@pytest.mark.django_db
def test_rejeu_dans_les_deux_minutes_meme_appareil(ask, check):
    """T1 : la réponse de verify s'est perdue ; le rejeu rend de nouveaux jetons, même session."""
    challenge = ask().json()
    code = last_code()
    first = check(challenge, code).json()
    replay = check(challenge, code)
    assert replay.status_code == 200
    assert replay.json()["tokens"]["refresh"] != first["tokens"]["refresh"]
    assert DeviceSession.objects.count() == 1
    assert check(challenge, code, install_id=INSTALL_B).json() == {"code": "otp_already_used"}
    OtpChallenge.objects.update(verified_at=timezone.now() - timedelta(minutes=3))
    assert check(challenge, code).json() == {"code": "otp_already_used"}


@pytest.mark.django_db
def test_rejeu_avec_un_mauvais_code(ask, check):
    challenge = ask().json()
    code = last_code()
    check(challenge, code)
    assert check(challenge, other_code(code)).json() == {"code": "otp_already_used"}


@durable_db
@pytest.mark.parametrize(
    ("champs", "code"),
    [
        ({"is_active": False, "deactivation_reason": "fraud"}, "account_disabled"),
        ({"is_staff": True}, "account_not_allowed"),
        ({"is_superuser": True}, "account_not_allowed"),
    ],
)
def test_etat_du_compte_apres_le_code(ask, check, user_factory, champs, code):
    user_factory(phone=PHONE, **champs)
    challenge = ask().json()
    response = check(challenge, last_code())
    assert response.status_code == 403
    assert response.json() == {"code": code}
    assert not DeviceSession.objects.exists()
    assert AuditEvent.objects.filter(action="accounts.otp.login_refused").count() == 1


@pytest.mark.django_db
def test_compte_dormant_restreint_sans_autres_appareils(ask, check, user_factory):
    from jeflink.accounts.sessions import create_session

    user = user_factory(phone=PHONE, display_name="Ancien Titulaire")
    User.objects.filter(pk=user.pk).update(created_at=timezone.now() - timedelta(days=200))
    create_session(user=user, app="web", platform="web", install_id=INSTALL_B)
    DeviceSession.objects.update(last_seen_at=timezone.now() - timedelta(days=90))
    challenge = ask().json()
    body = check(challenge, last_code(), install_id=INSTALL_A).json()
    assert body["restricted"] is True
    assert body["other_sessions"] == []
    assert body["restriction_kind"] == "client"
    assert body["user"]["display_name"] == "" and body["user"]["roles"] == []


@durable_db
def test_ops_sur_la_console_attend_le_second_facteur(ask, check, user_factory, settings):
    user = user_factory(phone=PHONE)
    grant_role(user=user, role=Role.OPS, reason_code="t", operator="a", second_operator="b")
    settings.ALLOWED_HOSTS = ["api", "testserver"]
    bff = {
        "HTTP_HOST": "api",
        "HTTP_X_JEFLINK_BFF": settings.BFF_SHARED_SECRETS[0],
        "HTTP_X_JEFLINK_APP": "console",
        "HTTP_X_JEFLINK_CLIENT_IP": "41.82.1.2",
    }
    challenge = ask(app=None, **bff).json()
    from django.test import Client

    payload = {
        "challenge_id": challenge["challenge_id"],
        "challenge_secret": challenge["challenge_secret"],
        "code": last_code(),
        "terms_version": settings.TERMS_VERSION,
        "device": {"platform": "web", "install_id": INSTALL_A},
    }

    def post():
        return Client().post(
            reverse("auth-otp-verify"), payload, content_type="application/json", **bff
        )

    response = post()
    body = response.json()
    # Aucune session avant le TOTP : seulement un jeton MFA (S1).
    assert set(body) == {"status", "mfa_token"}
    assert body["status"] == "mfa_enrollment_required"
    assert body["mfa_token"].startswith("jfm_")
    assert not DeviceSession.objects.exists()

    # Rejeu T1 (réponse perdue) : nouveau jeton MFA, l'ancien ne vaut plus.
    from jeflink.accounts.mfa import verify_totp
    from jeflink.common.errors import DomainError

    replay = post().json()
    assert replay["status"] == "mfa_enrollment_required"
    assert replay["mfa_token"] != body["mfa_token"]
    with pytest.raises(DomainError) as exc:
        verify_totp(mfa_token=body["mfa_token"], code="000000")
    assert exc.value.code == "mfa_token_invalid"


# --- Renvoi ----------------------------------------------------------------------------------


@pytest.mark.django_db
def test_renvoi(ask, api_client, check, django_capture_on_commit_callbacks):
    challenge = ask().json()
    first_code = last_code()
    payload = {k: challenge[k] for k in ("challenge_id", "challenge_secret")}
    url = reverse("auth-otp-resend")
    too_early = api_client.post(url, payload, format="json")
    assert too_early.status_code == 429
    assert too_early.json()["code"] == "otp_resend_too_early"

    for expected_remaining in (1, 0):
        OtpDelivery.objects.update(created_at=timezone.now() - timedelta(minutes=2))
        with django_capture_on_commit_callbacks(execute=True):
            response = api_client.post(url, payload, format="json")
        assert response.status_code == 202
        assert response.json()["deliveries_remaining"] == expected_remaining
        assert "challenge_secret" not in response.json()
    OtpDelivery.objects.update(created_at=timezone.now() - timedelta(minutes=2))
    assert api_client.post(url, payload, format="json").json()["code"] == "otp_resend_exhausted"
    # Un SMS en retard reste valable : l'ancien code fonctionne encore.
    assert check(challenge, first_code).status_code == 200


# --- Envoi par le worker ---------------------------------------------------------------------


class ScriptedGateway:
    name = "scripted"

    def __init__(self, *errors):
        self.errors = list(errors)
        self.bodies = []

    def send(self, *, to, body, idempotency_key, sender_id):
        from jeflink.notifications.sms import SmsResult

        self.bodies.append(body)
        if self.errors:
            raise self.errors.pop(0)
        return SmsResult(gateway=self.name, provider_message_id="m1", segments=1, status="sent")


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("error", "status", "code_kept"),
    [("SmsAmbiguousError", "unknown", True), ("SmsPermanentError", "failed", False)],
)
def test_erreurs_d_envoi(ask, monkeypatch, error, status, code_kept):
    from jeflink.accounts import tasks
    from jeflink.notifications import sms

    gateway = ScriptedGateway(getattr(sms, error)("E42"))
    monkeypatch.setattr(tasks, "get_sms_gateway", lambda: gateway)
    ask()
    delivery = OtpDelivery.objects.get()
    assert delivery.status == status
    assert delivery.error_code == "E42"
    assert bool(delivery.code_hash) is code_kept
    assert len(gateway.bodies) == 1  # jamais de nouvel essai : pas de double SMS


@pytest.mark.django_db
def test_erreur_transitoire_nouvel_essai_avec_un_nouveau_code(ask, monkeypatch):
    from jeflink.accounts import tasks
    from jeflink.notifications.sms import SmsTransientError

    gateway = ScriptedGateway(SmsTransientError("timeout"))
    monkeypatch.setattr(tasks, "get_sms_gateway", lambda: gateway)
    ask()
    assert len(gateway.bodies) == 2
    second = gateway.bodies[1].split(" est ")[1][:6]
    delivery = OtpDelivery.objects.get()
    assert delivery.status == "sent"
    assert delivery.code_hash == hash_code(delivery.public_id, second)


# --- Concurrence (S8) ----------------------------------------------------------------------


def _parallel(fn, count):
    results = []

    def run():
        try:
            results.append(fn())
        finally:
            connections.close_all()

    threads = [threading.Thread(target=run) for _ in range(count)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    return results


@durable_db
def test_vingt_verifications_concurrentes_au_plus_cinq_echecs(api_client):
    challenge = request_code(api_client).json()
    wrong = other_code(last_code())
    from rest_framework.test import APIClient

    codes = _parallel(lambda: verify(APIClient(), challenge, wrong).json()["code"], 20)
    assert OtpChallenge.objects.get().failed_attempts == 5
    assert OtpChallenge.objects.get().status == "locked"
    assert set(codes) <= {"otp_invalid", "otp_locked"}


@durable_db
def test_vingt_verifications_concurrentes_une_seule_session(api_client):
    challenge = request_code(api_client).json()
    code = last_code()
    from rest_framework.test import APIClient

    installs = iter([f"{i:08d}-0000-4000-8000-000000000000" for i in range(20)])
    lock = threading.Lock()

    def one():
        with lock:
            install_id = next(installs)
        return verify(APIClient(), challenge, code, install_id=install_id).status_code

    statuses = _parallel(one, 20)
    assert statuses.count(200) == 1
    assert DeviceSession.objects.count() == 1
    assert User.objects.count() == 1


# --- Revue sécurité des tâches 9 et 10 -------------------------------------------------------


@durable_db
def test_numero_bloque_ferme_les_challenges_deja_ouverts(api_client):
    """I1 : au 10e échec, les autres challenges ouverts du numéro deviennent inutilisables."""
    challenges = [request_code(api_client).json() for _ in range(3)]
    codes = [last_code()]  # code du dernier challenge seulement
    wrong = other_code(codes[0])
    for challenge in challenges[:2]:
        for _ in range(5):
            verify(api_client, challenge, wrong)
    spare = challenges[2]
    assert verify(api_client, spare, codes[0]).json() == {"code": "otp_locked"}
    assert OtpChallenge.objects.get(public_id=spare["challenge_id"]).status == "locked"
    assert not DeviceSession.objects.exists()


@pytest.mark.django_db
def test_renvoi_refuse_sur_un_numero_bloque(ask, api_client):
    from jeflink.accounts.models import OtpPhoneBlock
    from jeflink.common.pii import phone_hmac

    challenge = ask().json()
    OtpPhoneBlock.objects.create(
        phone_hmac=phone_hmac(PHONE), level=1, blocked_until=timezone.now() + timedelta(hours=1)
    )
    OtpDelivery.objects.update(created_at=timezone.now() - timedelta(minutes=2))
    payload = {k: challenge[k] for k in ("challenge_id", "challenge_secret")}
    response = api_client.post(reverse("auth-otp-resend"), payload, format="json")
    assert response.status_code == 429
    assert response.json()["code"] == "otp_rate_limited"


@pytest.mark.django_db
def test_relivraison_de_la_tache_ne_regenere_pas_le_code(ask):
    """I3 : worker arrêté en plein envoi, tâche relivrée : code gardé, issue « inconnue »."""
    from jeflink.accounts.tasks import send_otp

    ask()
    delivery = OtpDelivery.objects.get()
    OtpDelivery.objects.filter(pk=delivery.pk).update(status="sending")
    send_otp(str(delivery.public_id))
    delivery.refresh_from_db()
    assert delivery.status == "unknown"
    assert delivery.code_hash == hash_code(delivery.public_id, last_code())
    assert len(FakeSmsGateway.outbox) == 1


@pytest.mark.django_db
def test_demandes_simultanees_meme_cle(ask):
    """M2 : une demande déjà en cours avec la même clé ne crée pas de second challenge."""
    from jeflink.accounts.otp import _idempotency_cache_key
    from jeflink.common.ratelimit import client

    key = "cle-idempotence-simultanee-01"
    cache_key = _idempotency_cache_key(key, PHONE, "client:login", "")
    client().set(f"{cache_key}:lock", 1, ex=30)
    response = ask(key=key)
    assert response.status_code == 409
    assert response.json() == {"code": "otp_request_in_progress"}
    assert not OtpChallenge.objects.exists()


@pytest.mark.django_db
def test_cle_d_idempotence_trop_faible(ask):
    assert ask(key="courte-cle-16car").json() == {"code": "idempotency_key_required"}


@pytest.mark.django_db
def test_envoi_echoue_ne_revele_pas_la_joignabilite(ask, check, monkeypatch):
    """M7 : après un refus définitif du fournisseur, verify répond comme à un mauvais code."""
    from jeflink.accounts import tasks
    from jeflink.notifications.sms import SmsPermanentError

    monkeypatch.setattr(tasks, "get_sms_gateway", lambda: ScriptedGateway(SmsPermanentError("x")))
    challenge = ask().json()
    assert check(challenge, "123456").json()["code"] == "otp_invalid"


@pytest.mark.django_db
def test_chiffres_non_ascii_refuses(ask, check):
    challenge = ask().json()
    arabic = "".join(chr(0x0660 + int(d)) for d in last_code())
    assert check(challenge, arabic).json()["code"] == "invalid"
    assert OtpChallenge.objects.get().failed_attempts == 0


@pytest.mark.django_db
def test_gabarit_invalide_repli_sur_le_francais(ask, monkeypatch):
    """M9 : un gabarit wolof hors GSM-7 retombe sur le français, sans bloquer l'envoi."""
    from jeflink.accounts import tasks

    original = tasks.otp_sms_body

    def fragile(*, language, **kwargs):
        if language == "wo":
            raise ValueError("hors GSM-7")
        return original(language=language, **kwargs)

    monkeypatch.setattr(tasks, "otp_sms_body", fragile)
    ask(HTTP_ACCEPT_LANGUAGE="wo")
    assert OtpDelivery.objects.get().status == "sent"
    assert "votre code" in FakeSmsGateway.outbox[-1].body


@pytest.mark.django_db
def test_rejeu_limite_a_trois(ask, check):
    """M4 : trois rejeux au plus, chacun audité."""
    challenge = ask().json()
    code = last_code()
    check(challenge, code)
    assert [check(challenge, code).status_code for _ in range(4)] == [200, 200, 200, 409]
    replays = AuditEvent.objects.filter(action="accounts.otp.verified", metadata__replay=True)
    assert replays.count() == 3


@pytest.mark.django_db
def test_autres_appareils_sans_la_session_remplacee(ask, check, user_factory):
    """M6 : l'appareil qui se reconnecte ne se voit pas dans « autres appareils »."""
    from jeflink.accounts.sessions import create_session

    user = user_factory(phone=PHONE)
    create_session(user=user, app="client", platform="android", install_id=INSTALL_A)
    challenge = ask().json()
    body = check(challenge, last_code(), install_id=INSTALL_A).json()
    assert body["other_sessions"] == []


@durable_db
def test_un_bon_code_parmi_dix_neuf_mauvais_en_parallele(api_client):
    challenge = request_code(api_client).json()
    code = last_code()
    wrong = other_code(code)
    from rest_framework.test import APIClient

    attempts = iter([code] + [wrong] * 19)
    lock = threading.Lock()

    def one():
        with lock:
            value = next(attempts)
        return verify(APIClient(), challenge, value).status_code

    statuses = _parallel(one, 20)
    assert DeviceSession.objects.count() <= 1
    assert OtpChallenge.objects.get().failed_attempts <= 5
    assert statuses.count(200) <= 1
