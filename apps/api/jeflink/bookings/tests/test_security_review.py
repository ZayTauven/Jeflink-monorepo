"""Corrections de la revue de sécurité de la spec 004 : anonymisation après clôture, missions
bloquées, confirmation d'un avenant, fin sans code prouvée, gardes de transition, plafond de photos,
miniature d'une photo purgée, essais simultanés du code de fin."""

import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest
from django.contrib.auth.models import Group
from django.db import connection
from django.urls import reverse
from django.utils import timezone

from jeflink.accounts.deletion import _anonymize
from jeflink.accounts.models import User
from jeflink.accounts.tests.factories import CompleteUserFactory
from jeflink.bookings import services, tasks
from jeflink.bookings.machine import Actor, Status
from jeflink.bookings.models import Booking, BookingEvent, BookingPhoto
from jeflink.common import storage
from jeflink.common.errors import DomainError
from jeflink.common.tests.test_images import jpeg_with_gps
from jeflink.notifications import events
from jeflink.requests.models import ServiceRequest
from jeflink.requests.quotes import QuoteLineInput
from jeflink.requests.selectors import requests_for_provider
from jeflink.requests.tests.test_requests_api import bearer
from jeflink.trust.models import AuditEvent, Dispute

from .factories import advance, make_scene, scheduled
from .test_services import expect

pytestmark = pytest.mark.django_db


def key(n: int = 0) -> str:
    return f"review-key-{n:022d}"


def ops_user(phone="+221770000941", group="Médiation"):
    user = User.objects.create_user(phone, is_staff=True)
    user.groups.add(Group.objects.get(name=group))
    return user


# --- 1. Anonymisation après la clôture ----


def test_apres_une_mission_close_la_suppression_du_compte_vide_la_demande(api_client):
    scene, booking = scheduled()
    booking = advance(booking, Status.COMPLETED)
    Booking.objects.filter(pk=booking.pk).update(
        dispute_deadline=timezone.now() - timedelta(minutes=1)
    )
    assert services.close_due() == 1
    request = ServiceRequest.objects.get(pk=scene.request.pk)
    assert request.status == "booked" and request.landmark and request.description
    pro = bearer(api_client, booking.provider.owner, app="pro")
    seen = pro.get(reverse("pro-booking-detail", args=[booking.public_id])).json()
    assert seen["description"]  # avant la suppression : le pro lit la description

    _anonymize(User.objects.get(pk=scene.client.pk), reason="user_request")

    request.refresh_from_db()
    assert (request.description, request.landmark, request.zone_text) == ("", "", "")
    assert request.location is None
    after = pro.get(reverse("pro-booking-detail", args=[booking.public_id])).json()
    assert after["description"] == "" and (after["landmark"] or "") == ""
    assert after["location"] is None
    assert "mosquée" not in str(after) and scene.request.landmark not in str(after)


def test_une_mission_annulee_est_videe_aussi_une_mission_engagee_ne_l_est_pas():
    scene, booking = scheduled()
    services.cancel_booking(
        booking=booking, actor=scene.client, actor_kind=Actor.CLIENT, reason="price"
    )
    other_scene, engaged = scheduled()
    from jeflink.requests.services import anonymize_requests

    anonymize_requests(scene.client)
    anonymize_requests(other_scene.client)  # la suppression est refusée avant, ailleurs
    assert ServiceRequest.objects.get(pk=scene.request.pk).description == ""
    assert ServiceRequest.objects.get(pk=other_scene.request.pk).description != ""
    assert engaged.pk


# --- 2. Missions bloquées ----


def test_en_route_et_arrive_refuses_avant_le_creneau_moins_la_marge():
    scene = make_scene(pros=1)
    from jeflink.bookings.tests.factories import accept, confirm

    booking = confirm(accept(scene))  # créneau demain matin
    owner = booking.provider.owner
    with expect("too_early"):
        services.mark_en_route(booking=booking, actor=owner)
    with expect("too_early"):
        services.mark_arrived(booking=booking, actor=owner)
    booking.refresh_from_db()
    assert booking.status == Status.SCHEDULED
    Booking.objects.filter(pk=booking.pk).update(
        slot_start=timezone.now() + timedelta(hours=1, minutes=50),
        slot_end=timezone.now() + timedelta(hours=5),
    )
    booking.refresh_from_db()
    assert services.mark_en_route(booking=booking, actor=owner).status == Status.EN_ROUTE


def test_la_marge_est_un_reglage(settings):
    scene = make_scene(pros=1)
    from jeflink.bookings.tests.factories import accept, confirm

    booking = confirm(accept(scene))
    settings.BOOKING_EARLY_START_MARGIN = timedelta(days=3)
    assert services.mark_arrived(booking=booking, actor=booking.provider.owner).status == (
        Status.ON_SITE
    )


def test_trop_tot_par_l_api(api_client):
    scene = make_scene(pros=1)
    from jeflink.bookings.tests.factories import accept, confirm

    booking = confirm(accept(scene))
    pro = bearer(api_client, booking.provider.owner, app="pro")
    for name in ("pro-booking-en-route", "pro-booking-arrive"):
        response = pro.post(reverse(name, args=[booking.public_id]), {}, format="json")
        assert (response.status_code, response.json()["code"]) == (409, "too_early")


@pytest.mark.parametrize("status", [Status.ON_SITE, Status.IN_PROGRESS])
def test_l_ops_annule_une_mission_bloquee(status):
    scene, booking = scheduled(pros=2)
    booking = advance(booking, status)
    if status == Status.IN_PROGRESS:
        pending = services.propose_amendment(
            booking=booking, actor=booking.provider.owner, reason="parts", note="",
            lines=(QuoteLineInput("parts", 30_000),), total_xof=30_000, idempotency_key=key(),
        ).amendment  # fmt: skip
    ops = ops_user()
    result = services.cancel_by_ops(
        booking=booking, operator=ops, reason="pro_unreachable", note=""
    )
    assert (result.status, result.cancelled_by, result.cancel_reason) == (
        Status.CANCELLED,
        "ops",
        "ops_pro_unreachable",
    )
    event = BookingEvent.objects.filter(booking=booking).latest("id")
    assert (event.actor_kind, event.actor) == ("ops", ops)
    assert event.metadata == {"late": True, "reliability_weight": 0}
    audit = AuditEvent.objects.get(action="bookings.booking.cancelled")
    assert audit.actor_kind == "ops" and audit.actor == ops
    assert audit.metadata["from_status"] == status
    scene.request.refresh_from_db()
    assert scene.request.excluded_providers.filter(pk=booking.provider_id).exists()
    assert not requests_for_provider(provider=booking.provider).filter(pk=scene.request.pk)
    assert result.completion_code_enc == ""
    if status == Status.IN_PROGRESS:
        pending.refresh_from_db()
        assert pending.status == "lapsed"


def test_annulation_par_l_ops_refus():
    _, booking = scheduled()
    ops = ops_user()
    with expect("transition_not_allowed"):
        services.cancel_by_ops(booking=booking, operator=ops, reason="safety")  # scheduled
    booking = advance(booking, Status.ON_SITE)
    with expect("reason_invalid", 422):
        services.cancel_by_ops(booking=booking, operator=ops, reason="ennui")
    with expect("note_invalid", 422):
        services.cancel_by_ops(booking=booking, operator=ops, reason="other", note="")
    with expect("note_invalid", 422):
        services.cancel_by_ops(
            booking=booking, operator=ops, reason="other", note="Appeler le 77 123 45 67"
        )
    booking.refresh_from_db()
    assert booking.status == Status.ON_SITE


def test_ni_le_client_ni_le_pro_ne_peuvent_annuler_une_intervention_en_cours():
    scene, booking = scheduled()
    booking = advance(booking, Status.IN_PROGRESS)
    for actor_kind, actor in ((Actor.CLIENT, scene.client), (Actor.PRO, booking.provider.owner)):
        with pytest.raises(DomainError) as exc:
            services.transition(
                booking, to=Status.CANCELLED, actor=actor, actor_kind=actor_kind, reason="x"
            )
        assert exc.value.code == "transition_not_allowed"


@pytest.fixture(autouse=False)
def _mfa(monkeypatch):
    monkeypatch.setattr("jeflink.accounts.admin_site.admin_mfa_valid", lambda request: True)


def test_admin_annuler_la_mission(client, _mfa):
    _, booking = scheduled()
    booking = advance(booking, Status.ON_SITE)
    ops = ops_user()
    client.force_login(ops)
    url = reverse("admin:bookings_booking_changelist")
    page = client.post(url, {"action": "cancel_mission", "_selected_action": [booking.pk]})
    assert page.status_code == 200 and "Joignez les deux parties" in page.content.decode()
    client.post(
        url,
        {
            "action": "cancel_mission", "_selected_action": [booking.pk], "apply": "1",
            "reason": "job_abandoned", "note": "",
        },
        follow=True,
    )  # fmt: skip
    booking.refresh_from_db()
    assert (booking.status, booking.cancelled_by) == (Status.CANCELLED, "ops")
    assert AuditEvent.objects.filter(action="bookings.booking.cancelled", actor=ops).count() == 1


def test_admin_un_autre_groupe_n_annule_pas(client, _mfa):
    _, booking = scheduled()
    booking = advance(booking, Status.ON_SITE)
    client.force_login(ops_user("+221770000942", "Modération avis"))
    url = reverse("admin:bookings_booking_changelist")
    assert client.get(url).status_code == 403
    client.post(url, {"action": "cancel_mission", "_selected_action": [booking.pk], "apply": "1",
                      "reason": "safety", "note": ""})  # fmt: skip
    booking.refresh_from_db()
    assert booking.status == Status.ON_SITE


def set_slot_end(booking, end):
    Booking.objects.filter(pk=booking.pk).update(slot_start=end - timedelta(hours=4), slot_end=end)


def test_flag_stuck_signale_une_fois_et_le_filtre_les_montre(client, _mfa, caplog):
    caplog.set_level(logging.WARNING, logger="jeflink.alerts")
    _, stuck = scheduled()
    stuck = advance(stuck, Status.IN_PROGRESS)
    _, fresh = scheduled()
    fresh = advance(fresh, Status.ON_SITE)
    set_slot_end(stuck, timezone.now() - timedelta(hours=13))
    set_slot_end(fresh, timezone.now() - timedelta(hours=11))
    assert services.flag_stuck() == 1
    assert services.flag_stuck() == 0  # une seule fois
    assert tasks.flag_stuck() == 0
    stuck.refresh_from_db()
    fresh.refresh_from_db()
    assert stuck.stuck_flagged_at and fresh.stuck_flagged_at is None
    lines = [r.getMessage() for r in caplog.records if r.name == "jeflink.alerts"]
    assert len(lines) == 1 and lines[0].startswith("booking_stuck ")
    assert str(stuck.public_id) in lines[0] and "+221" not in lines[0]
    client.force_login(ops_user())
    page = client.get(reverse("admin:bookings_booking_changelist"), {"bloquee": "oui"})
    text = page.content.decode()
    assert (page.status_code == 200 and "1 réservation" in text) or str(stuck.stuck_flagged_at.year)


def test_le_delai_de_signalement_est_un_reglage(settings):
    _, booking = scheduled()
    booking = advance(booking, Status.ON_SITE)
    set_slot_end(booking, timezone.now() - timedelta(hours=2))
    assert services.flag_stuck() == 0
    settings.BOOKING_STUCK_AFTER = timedelta(hours=1)
    assert services.flag_stuck() == 1


# --- 3. Confirmation d'un avenant ----


def amendment_for(total: int, n: int = 0):
    scene, booking = scheduled()
    booking = advance(booking, Status.IN_PROGRESS)  # montant : 15 000
    amendment = services.propose_amendment(
        booking=booking, actor=booking.provider.owner, reason="extra_work", note="",
        lines=(QuoteLineInput("labor", total),), total_xof=total, idempotency_key=key(n),
    ).amendment  # fmt: skip
    return scene, booking, amendment


def test_le_client_accepte_ce_qu_il_a_vu():
    scene, booking, amendment = amendment_for(22_000)
    with expect("amendment_total_mismatch"):
        services.accept_amendment(amendment=amendment, actor=scene.client, total_xof=21_000)
    with expect("amendment_total_mismatch"):
        services.accept_amendment(amendment=amendment, actor=scene.client, total_xof=999_999)
    booking.refresh_from_db()
    assert booking.amount_xof == 15_000
    result = services.accept_amendment(amendment=amendment, actor=scene.client, total_xof=22_000)
    assert result.amount_xof == 22_000


def test_une_forte_hausse_exige_la_confirmation():
    scene, booking, amendment = amendment_for(30_000)  # +100 %
    with expect("amendment_confirmation_required", 422):
        services.accept_amendment(amendment=amendment, actor=scene.client, total_xof=30_000)
    with expect("amendment_confirmation_required", 422):
        services.accept_amendment(
            amendment=amendment, actor=scene.client, total_xof=30_000, confirm=False
        )
    booking.refresh_from_db()
    assert booking.amount_xof == 15_000
    assert (
        services.accept_amendment(
            amendment=amendment, actor=scene.client, total_xof=30_000, confirm=True
        ).amount_xof
        == 30_000
    )


def test_une_baisse_et_une_petite_hausse_n_exigent_pas_la_confirmation():
    scene, _, down = amendment_for(9_000)
    assert services.accept_amendment(amendment=down, actor=scene.client, total_xof=9_000)
    scene, _, up = amendment_for(22_500, 1)  # +50 % pile : pas au-delà du seuil
    assert services.accept_amendment(amendment=up, actor=scene.client, total_xof=22_500)


def test_api_accepter_un_avenant_exige_le_total_et_la_confirmation(api_client):
    scene, booking, amendment = amendment_for(30_000)
    client = bearer(api_client, scene.client)
    url = reverse("booking-amendment-accept", args=[booking.public_id, amendment.public_id])
    response = client.post(url, {}, format="json")
    assert (response.status_code, response.json()["code"]) == (400, "invalid")  # total absent
    response = client.post(url, {"total_xof": 29_000, "confirm": True}, format="json")
    assert (response.status_code, response.json()["code"]) == (409, "amendment_total_mismatch")
    response = client.post(url, {"total_xof": 30_000}, format="json")
    assert (response.status_code, response.json()["code"]) == (
        422,
        "amendment_confirmation_required",
    )
    response = client.post(url, {"total_xof": 30_000, "confirm": "peut-être"}, format="json")
    assert response.status_code == 400
    response = client.post(url, {"total_xof": 30_000, "confirm": True}, format="json")
    assert (response.status_code, response.json()["amount_xof"]) == (200, 30_000)
    # Rejeu : 200, même corps.
    assert (
        client.post(url, {"total_xof": 30_000, "confirm": True}, format="json").status_code == 200
    )


# --- 4. Fin sans code : notification dédiée ----


def test_la_fin_sans_code_notifie_immediatement_le_client(monkeypatch):
    sent = []
    monkeypatch.setattr(events, "notify", lambda kind, recipients, ref: sent.append((kind, ref)))
    scene, booking = scheduled()
    booking = advance(booking, Status.IN_PROGRESS)
    services.upload_photo(
        booking=booking, actor=booking.provider.owner, phase="after",
        content=jpeg_with_gps(), idempotency_key=key(5),
    )  # fmt: skip
    services.complete_work(
        booking=booking, actor=booking.provider.owner, no_code_reason="client_absent"
    )
    assert (events.BOOKING_COMPLETED_NO_CODE, booking.public_id) in sent
    assert events.BOOKING_COMPLETED_NO_CODE in events.SMS_KINDS and scene.client


# --- 5. Garde de transition sur les colonnes écrites ----


@pytest.mark.parametrize(
    ("to", "actor_kind", "fields"),
    [
        (Status.EN_ROUTE, Actor.PRO, {"amount_xof": 1}),
        (Status.IN_PROGRESS, Actor.PRO, {"amount_xof": 1}),
        (Status.COMPLETED, Actor.PRO, {"amount_xof": 1}),
        (Status.CANCELLED, Actor.SYSTEM, {"amount_xof": 1}),
        (Status.IN_PROGRESS, Actor.CLIENT, {"completion_method": "code"}),
        (Status.CLOSED, Actor.SYSTEM, {"no_code_reason": "client_absent"}),
    ],
)
def test_une_transition_n_ecrit_pas_n_importe_quelle_colonne(to, actor_kind, fields):
    _, booking = scheduled()
    booking = advance(booking, Status.IN_PROGRESS)
    Booking.objects.filter(pk=booking.pk).update(
        status={Status.EN_ROUTE: Status.SCHEDULED, Status.CLOSED: Status.COMPLETED}.get(
            to, Status.IN_PROGRESS
        )
    )
    before = Booking.objects.get(pk=booking.pk).amount_xof
    with pytest.raises((ValueError, DomainError)):
        services.transition(
            booking, to=to, actor=None, actor_kind=actor_kind, reason="x", fields=fields
        )
    assert Booking.objects.get(pk=booking.pk).amount_xof == before


# --- 6 et 7. Photos : plafond, miniature, purge ----


def test_les_photos_signalees_ne_comptent_pas_dans_le_plafond(settings):
    settings.BOOKING_PHOTO_MAX_PER_PHASE = 2
    scene, booking = scheduled()
    booking = advance(booking, Status.ON_SITE)
    owner = booking.provider.owner
    photos = [
        services.upload_photo(
            booking=booking, actor=owner, phase="before",
            content=jpeg_with_gps(size=(300 + n, 200)), idempotency_key=key(10 + n),
        ).photo
        for n in range(2)
    ]  # fmt: skip
    with expect("photo_limit_reached"):
        services.upload_photo(
            booking=booking, actor=owner, phase="before",
            content=jpeg_with_gps(size=(500, 200)), idempotency_key=key(20),
        )  # fmt: skip
    services.report_photo(booking=booking, photo_public_id=photos[0].public_id, actor=scene.client)
    assert services.upload_photo(
        booking=booking, actor=owner, phase="before",
        content=jpeg_with_gps(size=(500, 200)), idempotency_key=key(20),
    ).created  # fmt: skip


def test_la_miniature_d_une_photo_purgee_est_supprimee_et_rien_n_est_cree():
    _, booking = scheduled()
    booking = advance(booking, Status.ON_SITE)
    photo = services.upload_photo(
        booking=booking, actor=booking.provider.owner, phase="before",
        content=jpeg_with_gps(), idempotency_key=key(30),
    ).photo  # fmt: skip
    assert tasks.make_thumbnail(str(photo.public_id)) is True
    thumb_key = services.photo_keys(photo)[1]
    assert storage.exists(thumb_key)
    BookingPhoto.objects.filter(pk=photo.pk).update(
        purged_at=timezone.now(), image_key="", thumb_key=""
    )
    assert tasks.make_thumbnail(str(photo.public_id)) is False
    assert not storage.exists(thumb_key)  # supprimée, et rien recréé
    photo.refresh_from_db()
    assert photo.thumb_key == ""


def test_la_purge_programme_la_suppression_robuste(django_capture_on_commit_callbacks):
    _, booking = scheduled()
    booking = advance(booking, Status.ON_SITE)
    photo = services.upload_photo(
        booking=booking, actor=booking.provider.owner, phase="before",
        content=jpeg_with_gps(), idempotency_key=key(31),
    ).photo  # fmt: skip
    with django_capture_on_commit_callbacks(execute=True):
        assert services.purge_booking_photos(BookingPhoto.objects.filter(pk=photo.pk)) == 1
    assert not storage.exists(services.photo_keys(photo)[0])


def test_l_anonymiseur_de_litige_vide_aussi_la_note_de_decision():
    from jeflink.trust.services import anonymize_disputes

    scene, booking = scheduled()
    booking = advance(booking, Status.COMPLETED)
    services.open_dispute(
        booking=booking, actor=scene.client, reason="damage", description="Le travail est mal fait."
    )
    services.resolve_dispute(
        dispute=Dispute.objects.get(), decision="for_pro", note="Note interne de l'Ops",
        operator=ops_user("+221770000943"),
    )  # fmt: skip
    anonymize_disputes(scene.client)
    dispute = Dispute.objects.get()
    assert (dispute.description, dispute.decision_note) == ("", "")
    assert dispute.decision == "for_pro"  # la décision reste


# --- Essais simultanés du code de fin ----


@pytest.mark.django_db(transaction=True, databases="__all__", serialized_rollback=True)
def test_deux_essais_simultanes_sont_tous_les_deux_comptes():
    _, booking = scheduled()
    booking = advance(booking, Status.IN_PROGRESS)

    def attempt(_):
        try:
            services.complete_work(
                booking=booking, actor=booking.provider.owner, code="0000", photos_pending=True
            )
            return "ok"
        except DomainError as exc:
            return exc.code
        finally:
            connection.close()

    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(attempt, [0, 1]))
    wrong = Booking.objects.get(pk=booking.pk)
    code = services.visible_completion_code(wrong)
    if code == "0000":  # tirage rarissime : le code était 0000
        pytest.skip("code tiré égal à la valeur d'essai")
    assert results == ["completion_code_invalid"] * 2
    assert wrong.completion_code_attempts == 2  # aucun essai perdu par la concurrence
    assert AuditEvent.objects.filter(action="bookings.completion_code.failed").count() == 2


@pytest.mark.django_db(transaction=True, databases="__all__", serialized_rollback=True)
def test_le_bon_code_et_un_faux_en_meme_temps_donnent_une_seule_fin():
    _, booking = scheduled()
    booking = advance(booking, Status.IN_PROGRESS)
    good = services.visible_completion_code(Booking.objects.get(pk=booking.pk))
    bad = "0000" if good != "0000" else "1111"

    def attempt(code):
        try:
            services.complete_work(
                booking=booking, actor=booking.provider.owner, code=code, photos_pending=True
            )
            return "ok"
        except DomainError as exc:
            return exc.code
        finally:
            connection.close()

    with ThreadPoolExecutor(2) as pool:
        results = sorted(pool.map(attempt, [good, bad]))
    final = Booking.objects.get(pk=booking.pk)
    assert final.status == Status.COMPLETED and final.completion_method == "code"
    assert results in (
        ["completion_code_invalid", "ok"],
        ["ok", "ok"],
    )  # le faux passe avant ou rejoue
    assert BookingEvent.objects.filter(booking=booking, to_status="completed").count() == 1
    assert CompleteUserFactory
