"""Code de fin de mission (spec 004, tâche 4) : génération, chiffrement, essais limités, repli sans
code, régénération, SMS, et absence du code dans les réponses au pro, les logs et les audits."""

import json
import logging
import re
from datetime import timedelta

import pytest
from cryptography.fernet import Fernet
from django.urls import reverse

from jeflink.accounts.tests.factories import CompleteUserFactory
from jeflink.bookings import services
from jeflink.bookings.machine import Status
from jeflink.bookings.models import Booking, BookingEvent
from jeflink.common import crypto
from jeflink.common.secrets import secret_problems
from jeflink.common.tests.test_images import jpeg_with_gps
from jeflink.notifications import events
from jeflink.providers.models import Provider
from jeflink.providers.tests.factories import VerifiedProviderFactory
from jeflink.requests.tests.test_requests_api import bearer
from jeflink.trust.models import AuditEvent

from .factories import advance, scheduled
from .test_services import expect

pytestmark = pytest.mark.django_db
CODE = "7391"
WRONG = "1111"


@pytest.fixture(autouse=True)
def fixed_code(monkeypatch):
    """Un code connu, pour le chercher dans les logs et les audits."""
    monkeypatch.setattr(services, "generate_completion_code", lambda: CODE)


@pytest.fixture
def notified(monkeypatch):
    sent = []
    monkeypatch.setattr(
        events, "notify", lambda kind, recipients, ref: sent.append((kind, list(recipients), ref))
    )
    return sent


def in_progress():
    scene, booking = scheduled()
    return scene, advance(booking, Status.IN_PROGRESS)


_photo_counter = iter(range(10_000))


def complete(booking, **kwargs):
    """Termine ; une fin sans code (sauf ``code_locked``) se prouve par une vraie photo « après »
    (``photo=False`` pour ne pas en envoyer)."""
    photo = kwargs.pop("photo", True)
    kwargs.setdefault("photos_pending", True)
    reason = kwargs.get("no_code_reason")
    if photo and reason and reason != "code_locked":
        services.upload_photo(
            booking=booking, actor=booking.provider.owner, phase="after",
            content=jpeg_with_gps(size=(300 + next(_photo_counter), 200)),
            idempotency_key=f"complete-photo-{next(_photo_counter):020d}",
        )  # fmt: skip
    return services.complete_work(booking=booking, actor=booking.provider.owner, **kwargs)


def reload(booking) -> Booking:
    return Booking.objects.get(pk=booking.pk)


# --- Génération et chiffrement -----------------------------------------------------------------


def test_le_code_est_genere_a_scheduled_chiffre_et_lisible_du_client():
    _, booking = scheduled()
    assert booking.completion_code_enc.startswith("gAAAA")  # jeton Fernet, pas le code en clair
    assert crypto.decrypt(booking.completion_code_enc) == CODE
    assert services.visible_completion_code(booking) == CODE


def test_le_code_a_4_chiffres_par_defaut(monkeypatch):
    monkeypatch.undo()
    codes = {services.generate_completion_code() for _ in range(50)}
    assert all(len(c) == 4 and c.isdigit() for c in codes) and len(codes) > 10


def test_le_nombre_de_chiffres_est_un_reglage(settings, monkeypatch):
    monkeypatch.undo()
    settings.COMPLETION_CODE_DIGITS = 6
    assert len(services.generate_completion_code()) == 6


def test_le_code_est_efface_a_completed_et_a_cancelled():
    _, booking = in_progress()
    complete(booking, code=CODE)
    assert reload(booking).completion_code_enc == ""
    _, other = scheduled()
    services.cancel_booking(booking=other, actor=other.client, actor_kind="client", reason="price")
    assert reload(other).completion_code_enc == ""
    assert services.visible_completion_code(reload(other)) is None


@pytest.mark.parametrize(
    ("status", "visible"),
    [
        (Status.SCHEDULED, True),
        (Status.EN_ROUTE, True),
        (Status.ON_SITE, True),
        (Status.IN_PROGRESS, True),
        (Status.COMPLETED, False),
        (Status.CLOSED, False),
    ],
)
def test_visibilite_du_code_par_statut(status, visible):
    _, booking = scheduled()
    Booking.objects.filter(pk=booking.pk).update(status=status)
    assert (services.visible_completion_code(reload(booking)) is not None) is visible


def test_chiffrement_et_rotation_des_cles(settings):
    token = crypto.encrypt("1234")
    assert token != "1234" and crypto.decrypt(token) == "1234"
    new = Fernet.generate_key().decode()
    settings.DATA_ENCRYPTION_KEYS = [new, *settings.DATA_ENCRYPTION_KEYS]
    assert crypto.decrypt(token) == "1234"  # l'ancienne clé déchiffre encore
    assert crypto.decrypt(crypto.encrypt("5678")) == "5678"
    settings.DATA_ENCRYPTION_KEYS = [new]
    assert crypto.decrypt(token) is None and crypto.decrypt("") is None


# --- Clés au démarrage -------------------------------------------------------------------------


def test_les_cles_de_donnees_sont_controlees_au_demarrage(settings):
    assert secret_problems() == []
    settings.DATA_ENCRYPTION_KEYS = []
    assert any("DATA_ENCRYPTION_KEYS" in p for p in secret_problems())
    settings.DATA_ENCRYPTION_KEYS = ["pas-une-cle-fernet-mais-assez-longue-pour-passer"]
    assert any("DATA_ENCRYPTION_KEYS[0] : clé Fernet invalide" in p for p in secret_problems())
    settings.DATA_ENCRYPTION_KEYS = settings.MFA_ENCRYPTION_KEYS
    assert any("identique à" in p for p in secret_problems())


def test_la_cle_publique_de_dev_est_interdite_hors_local(settings):
    settings.DJANGO_ENV = "production"
    settings.S3_ENDPOINT = settings.S3_PUBLIC_ENDPOINT = "https://s3.example"
    settings.S3_BUCKET = settings.S3_ACCESS_KEY = settings.S3_SECRET_KEY = "x" * 30
    problems = secret_problems()
    assert any(p.startswith("DATA_ENCRYPTION_KEYS[0]") and "publique" in p for p in problems)


# --- Terminer avec le code ---------------------------------------------------------------------


def test_terminer_avec_le_bon_code(notified):
    scene, booking = in_progress()
    done = complete(booking, code=CODE)
    assert done.status == Status.COMPLETED and done.completion_method == "code"
    assert done.no_code_reason == "" and done.completed_at
    assert done.dispute_deadline - done.completed_at == timedelta(hours=48)
    event = BookingEvent.objects.filter(booking=booking).latest("id")
    assert event.metadata == {"completion_method": "code", "photos_pending": True}
    audit = AuditEvent.objects.get(action="bookings.booking.completed")
    assert audit.metadata == {"completion_method": "code", "no_code_reason": ""}
    assert (events.BOOKING_COMPLETED, [scene.client], booking.public_id) in notified


def test_un_code_faux_compte_un_essai_et_cinq_verrouillent():
    _, booking = in_progress()
    for expected in range(1, 5):
        with expect("completion_code_invalid", 422):
            complete(booking, code=WRONG)
        assert reload(booking).completion_code_attempts == expected
    with expect("completion_code_invalid", 422):
        complete(booking, code=WRONG)  # le 5e verrouille
    locked = reload(booking)
    assert locked.completion_code_locked and locked.completion_code_attempts == 5
    # Même le bon code est refusé une fois verrouillé.
    with expect("completion_code_locked", 409):
        complete(booking, code=CODE)
    assert reload(booking).status == Status.IN_PROGRESS
    failures = AuditEvent.objects.filter(action="bookings.completion_code.failed")
    assert [a.metadata["attempts"] for a in failures.order_by("id")] == [1, 2, 3, 4, 5]
    assert failures.latest("id").metadata["locked"] is True


def test_le_nombre_d_essais_est_un_reglage(settings):
    settings.COMPLETION_CODE_MAX_ATTEMPTS = 2
    _, booking = in_progress()
    for _ in range(2):
        with expect("completion_code_invalid", 422):
            complete(booking, code=WRONG)
    assert reload(booking).completion_code_locked


@pytest.mark.parametrize("bad", ["12", "12345", "abcd", "12 4", "٣٣٣٣"])
def test_un_code_mal_forme_ne_compte_pas_comme_un_essai(bad):
    _, booking = in_progress()
    with expect("completion_code_invalid", 422):
        complete(booking, code=bad)
    assert reload(booking).completion_code_attempts == 0


def test_la_regeneration_debloque_et_remet_les_essais_a_zero(monkeypatch):
    scene, booking = in_progress()
    for _ in range(5):
        with expect("completion_code_invalid", 422):
            complete(booking, code=WRONG)
    monkeypatch.setattr(services, "generate_completion_code", lambda: "2468")
    result = services.regenerate_completion_code(booking=booking, actor=scene.client)
    assert (result.completion_code_attempts, result.completion_code_locked) == (0, False)
    assert result.completion_code_regenerations == 1
    with expect("completion_code_invalid", 422):
        complete(booking, code=CODE)  # l'ancien code ne vaut plus
    assert complete(booking, code="2468").status == Status.COMPLETED
    assert AuditEvent.objects.get(action="bookings.completion_code.regenerated").metadata == {
        "regenerations": 1
    }


def test_trois_regenerations_au_plus():
    scene, booking = in_progress()
    for _ in range(3):
        services.regenerate_completion_code(booking=booking, actor=scene.client)
    with expect("completion_code_regen_limit", 409):
        services.regenerate_completion_code(booking=booking, actor=scene.client)


def test_regeneration_refusee_a_un_autre_compte_ou_hors_mission():
    scene, booking = in_progress()
    with expect("not_found", 404):
        services.regenerate_completion_code(booking=booking, actor=CompleteUserFactory())
    complete(booking, code=CODE)
    with expect("transition_not_allowed", 409):
        services.regenerate_completion_code(booking=booking, actor=scene.client)


# --- Terminer sans code ------------------------------------------------------------------------


def test_fin_sans_code_72_h_et_client_notifie(notified):
    scene, booking = in_progress()
    done = complete(booking, no_code_reason="client_absent")
    assert done.completion_method == "no_code" and done.no_code_reason == "client_absent"
    assert done.dispute_deadline - done.completed_at == timedelta(hours=72)
    assert BookingEvent.objects.filter(booking=booking).latest("id").metadata == {
        "completion_method": "no_code",
        "photos_pending": True,
    }
    assert (events.BOOKING_COMPLETED_NO_CODE, [scene.client], booking.public_id) in notified
    assert not any(kind == events.BOOKING_COMPLETED for kind, *_ in notified)
    assert AuditEvent.objects.get(action="bookings.booking.completed").metadata == {
        "completion_method": "no_code",
        "no_code_reason": "client_absent",
    }


def test_la_fenetre_sans_code_est_un_reglage(settings):
    settings.BOOKING_DISPUTE_WINDOW_NO_CODE = timedelta(hours=96)
    _, booking = in_progress()
    done = complete(booking, no_code_reason="client_no_phone")
    assert done.dispute_deadline - done.completed_at == timedelta(hours=96)


def test_code_locked_exige_un_code_verrouille():
    _, booking = in_progress()
    with expect("no_code_reason_invalid", 422):
        complete(booking, no_code_reason="code_locked")
    Booking.objects.filter(pk=booking.pk).update(completion_code_locked=True)
    assert complete(booking, no_code_reason="code_locked").status == Status.COMPLETED


def test_motif_inconnu_ni_code_ni_motif_ou_les_deux():
    _, booking = in_progress()
    with expect("no_code_reason_invalid", 422):
        complete(booking, no_code_reason="pas_envie")
    with expect("completion_proof_required", 422):
        complete(booking)
    with expect("completion_proof_required", 422):
        complete(booking, code=CODE, no_code_reason="client_absent")
    assert reload(booking).status == Status.IN_PROGRESS


# --- Photos « après » --------------------------------------------------------------------------


def test_sans_photo_ni_photos_pending_terminer_est_refuse():
    _, booking = in_progress()
    with expect("after_photos_required", 422):
        complete(booking, code=CODE, photos_pending=False)
    assert reload(booking).completion_code_attempts == 0  # ne brûle pas d'essai


@pytest.mark.parametrize("reason", ["client_refuses", "client_absent", "client_no_phone"])
def test_sans_code_une_photo_apres_recue_est_obligatoire(reason):
    """``photos_pending`` ne suffit plus pour une fin sans code (sauf ``code_locked``)."""
    _, booking = in_progress()
    with expect("after_photos_required", 422):
        complete(booking, no_code_reason=reason, photos_pending=True, photo=False)
    assert reload(booking).status == Status.IN_PROGRESS


def test_code_locked_garde_photos_pending():
    _, booking = in_progress()
    Booking.objects.filter(pk=booking.pk).update(completion_code_locked=True)
    assert complete(booking, no_code_reason="code_locked", photo=False).status == Status.COMPLETED


def test_une_photo_signalee_par_le_client_ne_prouve_plus_la_fin_sans_code():
    scene, booking = in_progress()
    photo = services.upload_photo(
        booking=booking, actor=booking.provider.owner, phase="after",
        content=jpeg_with_gps(size=(333, 200)), idempotency_key="complete-photo-" + "9" * 20,
    ).photo  # fmt: skip
    services.report_photo(booking=booking, photo_public_id=photo.public_id, actor=scene.client)
    with expect("after_photos_required", 422):
        complete(booking, no_code_reason="client_refuses", photo=False)
    # Le plafond ne compte pas la photo masquée : le pro peut en renvoyer une.
    assert complete(booking, no_code_reason="client_refuses").status == Status.COMPLETED


# --- Rejeu, permissions ------------------------------------------------------------------------


def test_terminer_deux_fois_ne_cree_aucun_evenement():
    _, booking = in_progress()
    complete(booking, code=CODE)
    before = BookingEvent.objects.filter(booking=booking).count()
    again = complete(booking, code=WRONG)  # même un autre corps : l'état courant
    assert again.status == Status.COMPLETED
    assert BookingEvent.objects.filter(booking=booking).count() == before


def test_un_pro_suspendu_peut_terminer_une_intervention_en_cours():
    _, booking = in_progress()
    Provider.objects.filter(pk=booking.provider_id).update(status="suspended")
    assert complete(booking, code=CODE).status == Status.COMPLETED


def test_autre_pro_et_mauvais_statut():
    _, booking = in_progress()
    with expect("not_found", 404):
        services.complete_work(
            booking=booking, actor=VerifiedProviderFactory().owner, code=CODE, photos_pending=True
        )
    _, early = scheduled()
    with expect("transition_not_allowed", 409):
        complete(early, code=CODE)


# --- SMS du code -------------------------------------------------------------------------------


def sms(notified):
    return [n for n in notified if n[0] == events.COMPLETION_CODE_SMS]


def test_un_sms_part_tout_seul_quand_le_pro_part(notified):
    scene, booking = scheduled()
    services.mark_en_route(booking=booking, actor=booking.provider.owner)
    assert sms(notified) == [(events.COMPLETION_CODE_SMS, [scene.client], booking.public_id)]
    assert reload(booking).completion_code_sms_sent == 1
    audit = AuditEvent.objects.get(action="bookings.completion_code.sms")
    assert audit.actor_kind == "system" and audit.metadata == {"automatic": True, "sent": 1}


def test_arrive_depuis_scheduled_envoie_aussi_le_sms_automatique(notified):
    _, booking = scheduled()
    services.mark_arrived(booking=booking, actor=booking.provider.owner)
    assert len(sms(notified)) == 1


def test_deux_sms_sur_demande_puis_429(notified):
    scene, booking = scheduled()
    services.mark_en_route(booking=booking, actor=booking.provider.owner)  # 1 automatique
    for _ in range(2):
        services.send_completion_code_sms(booking=booking, actor=scene.client)
    assert len(sms(notified)) == 3
    with expect("sms_limit_reached", 429):
        services.send_completion_code_sms(booking=booking, actor=scene.client)
    assert len(sms(notified)) == 3


def test_les_sms_sur_demande_avant_le_depart_ne_mangent_pas_l_automatique(notified):
    scene, booking = scheduled()
    for _ in range(2):
        services.send_completion_code_sms(booking=booking, actor=scene.client)
    with expect("sms_limit_reached", 429):
        services.send_completion_code_sms(booking=booking, actor=scene.client)
    services.mark_en_route(booking=booking, actor=booking.provider.owner)
    assert len(sms(notified)) == 3  # 2 sur demande, puis l'automatique


def test_sms_refuse_a_un_autre_compte_ou_apres_la_fin():
    scene, booking = in_progress()
    with expect("not_found", 404):
        services.send_completion_code_sms(booking=booking, actor=CompleteUserFactory())
    complete(booking, code=CODE)
    with expect("transition_not_allowed", 409):
        services.send_completion_code_sms(booking=booking, actor=scene.client)


# --- Le code n'apparaît nulle part où il ne doit pas -------------------------------------------

TOKEN = re.compile(rf"(?<![0-9A-Za-z-]){CODE}(?![0-9A-Za-z-])")


def test_le_code_n_est_ni_dans_les_logs_ni_dans_les_audits(caplog, notified):
    caplog.set_level(logging.DEBUG)
    scene, booking = scheduled()
    services.mark_en_route(booking=booking, actor=booking.provider.owner)
    services.send_completion_code_sms(booking=booking, actor=scene.client)
    services.mark_arrived(booking=booking, actor=booking.provider.owner)
    services.start_work(booking=booking, actor=booking.provider.owner, photos_pending=True)
    for _ in range(5):
        with expect("completion_code_invalid", 422):
            complete(booking, code=WRONG)
    services.regenerate_completion_code(booking=booking, actor=scene.client)
    services.complete_work(
        booking=booking, actor=booking.provider.owner, code=CODE, photos_pending=True
    )
    texts = [r.getMessage() for r in caplog.records]
    assert not [t for t in texts if TOKEN.search(t)]
    assert not [t for t in texts if WRONG in t and "completion" in t]
    dumped = json.dumps(
        [
            [a.action, a.metadata, str(a.target_public_id), a.actor_kind]
            for a in AuditEvent.objects.all()
        ]
    )
    assert not TOKEN.search(dumped) and WRONG not in dumped
    events_dump = json.dumps(list(BookingEvent.objects.values("reason", "note", "metadata")))
    assert not TOKEN.search(events_dump)


def test_l_adaptateur_log_n_ecrit_pas_le_code(caplog, django_capture_on_commit_callbacks):
    """Avec l'adaptateur ``log`` réel : une ligne par notification, type et identifiants."""
    caplog.set_level(logging.INFO, logger="jeflink.notifications.events")
    scene, booking = scheduled()
    with django_capture_on_commit_callbacks(execute=True):
        services.mark_en_route(booking=booking, actor=booking.provider.owner)
    lines = [r.getMessage() for r in caplog.records]
    assert any("kind=completion_code.sms" in line for line in lines)
    text = " ".join(lines)
    assert TOKEN.search(text) is None and scene.client.phone not in text


# --- API ---------------------------------------------------------------------------------------


def complete_url(booking):
    return reverse("pro-booking-complete", args=[booking.public_id])


def test_api_terminer_avec_le_code_et_le_pro_ne_voit_jamais_le_code(api_client):
    scene, booking = in_progress()
    client_api = bearer(api_client, scene.client)
    pro_api = bearer(api_client, booking.provider.owner, app="pro")
    seen = client_api.get(reverse("booking-detail", args=[booking.public_id])).json()
    assert seen["completion_code"] == CODE and seen["completion_code_locked"] is False
    assert seen["can_regenerate_completion_code"] is True
    pro_view = pro_api.get(reverse("pro-booking-detail", args=[booking.public_id]))
    assert (
        "completion_code" not in pro_view.json() and TOKEN.search(pro_view.content.decode()) is None
    )
    response = pro_api.post(
        complete_url(booking), {"code": CODE, "photos_pending": True}, format="json"
    )
    data = response.json()
    assert (response.status_code, data["status"], data["completion_method"]) == (
        200,
        "completed",
        "code",
    )
    assert data["dispute_deadline"] and "completion_code" not in data
    assert TOKEN.search(response.content.decode()) is None
    after = client_api.get(reverse("booking-detail", args=[booking.public_id])).json()
    assert after["completion_code"] is None
    # Rejeu : 200.
    assert pro_api.post(complete_url(booking), {"code": CODE}, format="json").status_code == 200


def test_api_erreurs_de_terminaison(api_client):
    scene, booking = in_progress()
    pro_api = bearer(api_client, booking.provider.owner, app="pro")
    url = complete_url(booking)
    cases = [
        ({"photos_pending": True}, 422, "completion_proof_required"),
        ({"code": WRONG, "photos_pending": True}, 422, "completion_code_invalid"),
        ({"code": CODE}, 422, "after_photos_required"),
        ({"no_code_reason": "peut-etre", "photos_pending": True}, 422, "no_code_reason_invalid"),
        ({"code": CODE, "photos_pending": "x"}, 400, "invalid"),
    ]
    for body, status, code in cases:
        response = pro_api.post(url, body, format="json")
        assert (response.status_code, response.json()["code"]) == (status, code), body
        assert WRONG not in response.content.decode()  # jamais d'écho de la saisie
    for _ in range(4):
        pro_api.post(url, {"code": WRONG, "photos_pending": True}, format="json")
    locked = pro_api.post(url, {"code": CODE, "photos_pending": True}, format="json")
    assert (locked.status_code, locked.json()["code"]) == (409, "completion_code_locked")
    fallback = pro_api.post(
        url, {"no_code_reason": "code_locked", "photos_pending": True}, format="json"
    )
    assert fallback.status_code == 200 and fallback.json()["completion_method"] == "no_code"
    assert scene.client


def test_api_terminer_refuse_au_client_a_un_autre_pro_et_sans_session(api_client):
    scene, booking = in_progress()
    url = complete_url(booking)
    body = {"code": CODE, "photos_pending": True}
    assert bearer(api_client, scene.client).post(url, body, format="json").status_code == 403
    stranger = bearer(api_client, VerifiedProviderFactory().owner, app="pro")
    assert stranger.post(url, body, format="json").status_code == 404
    api_client.credentials()
    assert api_client.post(url, body, format="json").status_code == 401


def test_api_un_pro_suspendu_termine(api_client):
    _, booking = in_progress()
    Provider.objects.filter(pk=booking.provider_id).update(status="suspended")
    response = bearer(api_client, booking.provider.owner, app="pro").post(
        complete_url(booking), {"code": CODE, "photos_pending": True}, format="json"
    )
    assert response.status_code == 200


def test_api_regenerer_et_demander_un_sms(api_client, notified):
    scene, booking = scheduled()
    api = bearer(api_client, scene.client)
    regen = reverse("booking-code-regenerate", args=[booking.public_id])
    sms_url = reverse("booking-code-sms", args=[booking.public_id])
    assert api.post(regen).status_code == 200
    assert api.get(reverse("booking-detail", args=[booking.public_id])).json()[
        "can_send_completion_code_sms"
    ]
    assert api.post(sms_url).status_code == 200 and api.post(sms_url).status_code == 200
    response = api.post(sms_url)
    assert (response.status_code, response.json()["code"]) == (429, "sms_limit_reached")
    for _ in range(2):
        api.post(regen)
    response = api.post(regen)
    assert (response.status_code, response.json()["code"]) == (409, "completion_code_regen_limit")
    other = bearer(api_client, CompleteUserFactory())
    assert other.post(regen).status_code == 404 and other.post(sms_url).status_code == 404
    pro = bearer(api_client, booking.provider.owner, app="pro")
    assert pro.post(regen).status_code == 404  # le pro n'est pas le client de la réservation
    api_client.credentials()
    assert api_client.post(sms_url).status_code == 401


# --- Admin : part de fins sans code par pro ----------------------------------------------------


def test_l_admin_montre_la_part_de_fins_sans_code(client, monkeypatch):
    from django.contrib.auth.models import Group
    from django.urls import reverse as rev

    from jeflink.accounts.models import User

    monkeypatch.setattr("jeflink.accounts.admin_site.admin_mfa_valid", lambda request: True)
    _, first = in_progress()
    complete(first, no_code_reason="client_absent")
    Booking.objects.filter(pk=first.pk).update(status=Status.CLOSED)
    ops = User.objects.create_user("+221770000888", is_staff=True)
    ops.groups.add(Group.objects.get(name="Validation pros"))
    client.force_login(ops)
    page = client.get(rev("admin:providers_provider_changelist"))
    assert page.status_code == 200 and "1 / 1" in page.content.decode()
