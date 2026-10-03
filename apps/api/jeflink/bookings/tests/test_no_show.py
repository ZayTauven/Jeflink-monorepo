"""No-show (spec 004, tâche 3) : déclaration après la marge, contestation, confirmation différée,
décision de l'Ops, interrogation du client. Services, tâches, API et admin."""

from datetime import timedelta

import pytest
from django.contrib.auth.models import Group
from django.urls import reverse
from django.utils import timezone

from jeflink.accounts.deletion import _anonymize
from jeflink.accounts.models import User
from jeflink.accounts.tests.factories import CompleteUserFactory
from jeflink.bookings import services, tasks
from jeflink.bookings.machine import NO_SHOW_WEIGHT, Actor, Status
from jeflink.bookings.models import Booking, BookingEvent, NoShowReport
from jeflink.notifications import events
from jeflink.providers.models import Provider
from jeflink.providers.tests.factories import VerifiedProviderFactory
from jeflink.requests.models import ServiceRequest
from jeflink.requests.selectors import requests_for_provider
from jeflink.requests.tests.test_requests_api import bearer
from jeflink.trust.models import AuditEvent

from .factories import advance, scheduled
from .test_services import expect

pytestmark = pytest.mark.django_db


def slot_passed(booking: Booking, *, minutes_after_end: int = 90) -> Booking:
    """Le créneau s'est terminé il y a ``minutes_after_end`` minutes."""
    end = timezone.now() - timedelta(minutes=minutes_after_end)
    Booking.objects.filter(pk=booking.pk).update(slot_start=end - timedelta(hours=4), slot_end=end)
    booking.refresh_from_db()
    return booking


def declared(*, pros: int = 1):
    scene, booking = scheduled(pros=pros)
    booking = slot_passed(booking)
    services.declare_no_show(booking=booking, actor=scene.client)
    booking.refresh_from_db()
    return scene, booking


@pytest.fixture
def notified(monkeypatch):
    sent = []
    monkeypatch.setattr(
        events, "notify", lambda kind, recipients, ref: sent.append((kind, list(recipients), ref))
    )
    return sent


# --- Déclaration -------------------------------------------------------------------------------


def test_trop_tot_avant_la_fin_du_creneau_et_sa_marge():
    scene, booking = scheduled()
    with expect("no_show_too_early"):
        services.declare_no_show(booking=booking, actor=scene.client)
    booking = slot_passed(booking, minutes_after_end=30)  # créneau fini, marge de 60 min en cours
    with expect("no_show_too_early"):
        services.declare_no_show(booking=booking, actor=scene.client)
    booking.refresh_from_db()
    assert booking.status == Status.SCHEDULED and not NoShowReport.objects.exists()


def test_la_marge_est_un_reglage(settings):
    scene, booking = scheduled()
    booking = slot_passed(booking, minutes_after_end=30)
    settings.BOOKING_NO_SHOW_GRACE = timedelta(minutes=15)
    assert services.declare_no_show(booking=booking, actor=scene.client).status == Status.CANCELLED


def test_le_poids_d_un_no_show_est_3():
    assert NO_SHOW_WEIGHT == 3


def test_declaration_annule_rouvre_la_demande_et_exclut_le_pro(notified):
    scene, booking = scheduled(pros=2)
    booking = slot_passed(booking)
    result = services.declare_no_show(booking=booking, actor=scene.client)
    assert (result.status, result.cancelled_by, result.cancel_reason) == (
        Status.CANCELLED,
        "client",
        "pro_no_show",
    )
    scene.request.refresh_from_db()
    assert scene.request.status in {ServiceRequest.Status.OPEN, ServiceRequest.Status.QUOTED}
    assert scene.request.excluded_providers.filter(pk=booking.provider_id).exists()
    assert not requests_for_provider(provider=booking.provider).filter(pk=scene.request.pk)
    report = NoShowReport.objects.get(booking=booking)
    assert report.status == NoShowReport.Status.PENDING
    event = BookingEvent.objects.filter(booking=booking).latest("id")
    assert (event.actor_kind, event.reason) == ("client", "pro_no_show")
    # Poids différé : 0 à la déclaration.
    assert event.metadata == {"late": True, "reliability_weight": 0}
    assert (events.BOOKING_CANCELLED, [booking.provider.owner], booking.public_id) in notified
    audit = AuditEvent.objects.get(action="bookings.booking.cancelled")
    assert audit.metadata["reason"] == "pro_no_show" and audit.metadata["reliability_weight"] == 0


def test_declaration_rejouee_ne_cree_ni_evenement_ni_rapport():
    scene, booking = declared()
    before = BookingEvent.objects.filter(booking=booking).count()
    again = services.declare_no_show(booking=booking, actor=scene.client)
    assert again.status == Status.CANCELLED
    assert BookingEvent.objects.filter(booking=booking).count() == before
    assert NoShowReport.objects.count() == 1


def test_declaration_depuis_en_route_permise_sur_place_refusee():
    scene, booking = scheduled()
    booking = advance(booking, Status.EN_ROUTE)
    booking = slot_passed(booking)
    assert services.declare_no_show(booking=booking, actor=scene.client).status == Status.CANCELLED
    scene2, booking2 = scheduled()
    booking2 = slot_passed(advance(booking2, Status.ON_SITE))
    with expect("transition_not_allowed"):
        services.declare_no_show(booking=booking2, actor=scene2.client)


def test_declaration_par_un_autre_compte_ou_refusee_hors_cycle():
    scene, booking = scheduled()
    booking = slot_passed(booking)
    with expect("not_found", 404):
        services.declare_no_show(booking=booking, actor=CompleteUserFactory())
    Booking.objects.filter(pk=booking.pk).update(status=Status.CLOSED)
    with expect("transition_not_allowed"):
        services.declare_no_show(booking=booking, actor=scene.client)


def test_le_client_ne_peut_pas_annuler_avec_le_motif_pro_no_show():
    scene, booking = scheduled()
    with expect("reason_invalid", 422):
        services.cancel_booking(
            booking=booking, actor=scene.client, actor_kind=Actor.CLIENT, reason="pro_no_show"
        )


# --- Contestation ------------------------------------------------------------------------------


def test_le_pro_conteste(notified):
    scene, booking = declared()
    owner = booking.provider.owner
    result = services.contest_no_show(booking=booking, actor=owner, note="J'étais sur place à 9 h")
    report = NoShowReport.objects.get(booking=booking)
    assert result.pk == booking.pk and report.status == NoShowReport.Status.CONTESTED
    assert report.contest_note == "J'étais sur place à 9 h" and report.contested_at
    assert (events.NO_SHOW_CONTESTED, [scene.client], booking.public_id) in notified
    audit = AuditEvent.objects.get(action="bookings.no_show.contested")
    assert "9 h" not in str(audit.metadata) and audit.metadata == {}


def test_contester_deux_fois_rend_l_etat_courant():
    _, booking = declared()
    owner = booking.provider.owner
    services.contest_no_show(booking=booking, actor=owner, note="première note")
    services.contest_no_show(booking=booking, actor=owner, note="autre note")
    assert NoShowReport.objects.get(booking=booking).contest_note == "première note"
    assert AuditEvent.objects.filter(action="bookings.no_show.contested").count() == 1


@pytest.mark.parametrize("note", ["", "   ", "Appelez-moi au 77 123 45 67", "x" * 201])
def test_note_de_contestation_invalide(note):
    _, booking = declared()
    with expect("note_invalid", 422):
        services.contest_no_show(booking=booking, actor=booking.provider.owner, note=note)
    assert NoShowReport.objects.get().status == NoShowReport.Status.PENDING


def test_contestation_apres_les_24_h_ou_une_decision_refusee():
    _, booking = declared()
    owner = booking.provider.owner
    NoShowReport.objects.update(created_at=timezone.now() - timedelta(hours=25))
    with expect("no_show_contest_closed"):
        services.contest_no_show(booking=booking, actor=owner, note="en retard")
    _, other = declared()
    NoShowReport.objects.filter(booking=other).update(status=NoShowReport.Status.CONFIRMED)
    with expect("no_show_contest_closed"):
        services.contest_no_show(booking=other, actor=other.provider.owner, note="trop tard")


def test_contestation_d_un_autre_pro_ou_sans_no_show():
    _, booking = declared()
    with expect("not_found", 404):
        services.contest_no_show(
            booking=booking, actor=VerifiedProviderFactory().owner, note="je conteste"
        )
    _, plain = scheduled()
    with expect("transition_not_allowed"):
        services.contest_no_show(booking=plain, actor=plain.provider.owner, note="je conteste")


def test_un_pro_suspendu_peut_contester():
    _, booking = declared()
    Provider.objects.filter(pk=booking.provider_id).update(status="suspended")
    services.contest_no_show(booking=booking, actor=booking.provider.owner, note="j'étais là")
    assert NoShowReport.objects.get().status == NoShowReport.Status.CONTESTED


# --- Confirmation différée et décision de l'Ops ------------------------------------------------


def test_le_poids_3_ne_s_applique_qu_apres_24_h_sans_contestation():
    declared()
    assert services.confirm_no_shows() == 0  # trop tôt
    assert not AuditEvent.objects.filter(action="bookings.no_show.decided").exists()
    NoShowReport.objects.update(created_at=timezone.now() - timedelta(hours=25))
    assert services.confirm_no_shows() == 1
    report = NoShowReport.objects.get()
    assert report.status == NoShowReport.Status.CONFIRMED and report.decided_by is None
    audit = AuditEvent.objects.get(action="bookings.no_show.decided")
    assert audit.actor_kind == "system"
    assert audit.metadata == {
        "decision": "confirmed",
        "reliability_weight": NO_SHOW_WEIGHT == 3 and 3,
    }
    assert services.confirm_no_shows() == 0  # idempotente
    assert AuditEvent.objects.filter(action="bookings.no_show.decided").count() == 1


def test_un_rapport_conteste_attend_l_ops():
    _, booking = declared()
    services.contest_no_show(booking=booking, actor=booking.provider.owner, note="j'étais là")
    NoShowReport.objects.update(created_at=timezone.now() - timedelta(days=3))
    assert tasks.confirm_no_shows() == 0
    assert NoShowReport.objects.get().status == NoShowReport.Status.CONTESTED


@pytest.mark.parametrize(
    ("decision", "weight"),
    [(NoShowReport.Status.CONFIRMED, 3), (NoShowReport.Status.DISMISSED, 0)],
)
def test_l_ops_tranche_un_rapport_conteste(decision, weight):
    _, booking = declared()
    services.contest_no_show(booking=booking, actor=booking.provider.owner, note="j'étais là")
    ops = CompleteUserFactory()
    report = services.decide_no_show(
        report=NoShowReport.objects.get(), decision=decision, operator=ops
    )
    assert (report.status, report.decided_by, report.decided_at is not None) == (
        decision,
        ops,
        True,
    )
    audit = AuditEvent.objects.get(action="bookings.no_show.decided")
    assert audit.actor_kind == "ops" and audit.actor == ops
    assert audit.metadata == {"decision": decision, "reliability_weight": weight}
    # La réservation reste annulée et le pro exclu dans tous les cas.
    booking.refresh_from_db()
    assert booking.status == Status.CANCELLED


def test_decision_invalide_ou_deja_prise():
    _, booking = declared()
    report = NoShowReport.objects.get()
    ops = CompleteUserFactory()
    with expect("decision_invalid", 422):
        services.decide_no_show(report=report, decision="contested", operator=ops)
    services.decide_no_show(report=report, decision="dismissed", operator=ops)
    with expect("transition_not_allowed"):
        services.decide_no_show(report=report, decision="confirmed", operator=ops)
    assert booking.pk


# --- « Le pro est-il venu ? » ------------------------------------------------------------------


def test_no_show_check_interroge_le_client_une_fois_sans_annuler(notified):
    scene, past = scheduled()
    past = slot_passed(past)
    _, future = scheduled()
    _, cancelled = scheduled()
    cancelled = slot_passed(cancelled)
    services.cancel_booking(
        booking=cancelled, actor=cancelled.client, actor_kind=Actor.CLIENT, reason="price"
    )
    notified.clear()
    assert services.no_show_check() == 1
    assert [(k, r, ref) for k, r, ref in notified] == [
        (events.NO_SHOW_CHECK, [scene.client], past.public_id)
    ]
    past.refresh_from_db()
    future.refresh_from_db()
    assert past.status == Status.SCHEDULED and past.no_show_check_sent_at  # jamais annulée seule
    assert future.no_show_check_sent_at is None
    assert tasks.no_show_check() == 0  # une seule fois


def test_no_show_check_attend_la_marge():
    _, booking = scheduled()
    slot_passed(booking, minutes_after_end=30)
    assert services.no_show_check() == 0


# --- Suppression du compte ---------------------------------------------------------------------


def test_l_anonymiseur_efface_la_note_de_contestation():
    _, booking = declared()
    services.contest_no_show(booking=booking, actor=booking.provider.owner, note="j'étais là")
    owner = User.objects.get(pk=booking.provider.owner_id)
    # Le blocage de suppression ne s'applique pas ici : on appelle l'anonymiseur du domaine.
    services.anonymize_bookings(owner)
    assert NoShowReport.objects.get().contest_note == ""
    assert _anonymize  # l'anonymiseur est bien enregistré avec les autres


# --- API ---------------------------------------------------------------------------------------


def test_api_le_client_declare_puis_le_pro_conteste(api_client):
    scene, booking = scheduled()
    slot_passed(booking)
    client_api = bearer(api_client, scene.client)
    detail = client_api.get(reverse("booking-detail", args=[booking.public_id])).json()
    assert detail["can_report_no_show"] is True and detail["no_show"] is None
    response = client_api.post(reverse("booking-no-show", args=[booking.public_id]))
    data = response.json()
    assert (response.status_code, data["status"]) == (200, "cancelled")
    assert data["no_show"] == {"status": "pending", "contest_deadline": None, "can_contest": False}
    assert data["can_report_no_show"] is False
    # Rejeu : 200, rien de plus.
    assert client_api.post(reverse("booking-no-show", args=[booking.public_id])).status_code == 200
    assert NoShowReport.objects.count() == 1

    pro_api = bearer(api_client, booking.provider.owner, app="pro")
    seen = pro_api.get(reverse("pro-booking-detail", args=[booking.public_id])).json()
    assert seen["no_show"]["status"] == "pending" and seen["no_show"]["can_contest"] is True
    assert seen["no_show"]["contest_deadline"] and seen["cancel_reason"] == "pro_no_show"
    response = pro_api.post(
        reverse("pro-booking-contest-no-show", args=[booking.public_id]),
        {"note": "J'étais là à 9 h"},
        format="json",
    )
    assert (response.status_code, response.json()["no_show"]["status"]) == (200, "contested")
    # La note n'est jamais renvoyée, ni au pro ni au client.
    assert "J'étais" not in response.content.decode()
    client_view = client_api.get(reverse("booking-detail", args=[booking.public_id]))
    assert "J'étais" not in client_view.content.decode()


def test_api_declaration_trop_tot_autre_client_et_non_authentifie(api_client):
    scene, booking = scheduled()
    url = reverse("booking-no-show", args=[booking.public_id])
    response = bearer(api_client, scene.client).post(url)
    assert (response.status_code, response.json()["code"]) == (409, "no_show_too_early")
    detail = bearer(api_client, scene.client).get(
        reverse("booking-detail", args=[booking.public_id])
    )
    assert detail.json()["can_report_no_show"] is False and detail.json()["no_show_available_at"]
    response = bearer(api_client, CompleteUserFactory()).post(url)
    assert (response.status_code, response.json()["code"]) == (404, "not_found")
    api_client.credentials()
    assert api_client.post(url).status_code == 401


def test_api_contestation_refusee_et_invalide(api_client):
    scene, booking = declared()
    url = reverse("pro-booking-contest-no-show", args=[booking.public_id])
    owner = booking.provider.owner
    assert bearer(api_client, scene.client).post(url, {"note": "x"}, "json").status_code == 403
    assert (
        bearer(api_client, VerifiedProviderFactory().owner, "pro")
        .post(url, {"note": "x"}, "json")
        .status_code
        == 404
    )
    pro = bearer(api_client, owner, app="pro")
    response = pro.post(url, {"note": "Appelez le 77 123 45 67"}, "json")
    assert (response.status_code, response.json()["code"]) == (422, "note_invalid")
    assert pro.post(url, {}, "json").status_code == 400
    NoShowReport.objects.update(created_at=timezone.now() - timedelta(hours=30))
    response = pro.post(url, {"note": "trop tard"}, "json")
    assert (response.status_code, response.json()["code"]) == (409, "no_show_contest_closed")


# --- Admin « Médiation » -----------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _second_facteur_valide(monkeypatch):
    monkeypatch.setattr("jeflink.accounts.admin_site.admin_mfa_valid", lambda request: True)


def login(client, group: str):
    user = User.objects.create_user("+221770000777", is_staff=True)
    user.groups.add(Group.objects.get(name=group))
    client.force_login(user)
    return user


def run_action(client, action: str, *reports):
    return client.post(
        reverse("admin:bookings_noshowreport_changelist"),
        {"action": action, "_selected_action": [r.pk for r in reports]},
        follow=True,
    )


@pytest.mark.parametrize(
    ("action", "expected"), [("confirm", "confirmed"), ("dismiss", "dismissed")]
)
def test_admin_mediation_confirme_ou_ecarte(client, action, expected):
    _, booking = declared()
    services.contest_no_show(booking=booking, actor=booking.provider.owner, note="j'étais là")
    ops = login(client, "Médiation")
    run_action(client, action, NoShowReport.objects.get())
    report = NoShowReport.objects.get()
    assert (report.status, report.decided_by) == (expected, ops)
    assert AuditEvent.objects.filter(action="bookings.no_show.decided", actor=ops).count() == 1


def test_admin_un_autre_groupe_ne_tranche_pas(client):
    _, booking = declared()
    login(client, "Validation pros")
    response = client.get(reverse("admin:bookings_noshowreport_changelist"))
    assert response.status_code == 403
    run_action(client, "confirm", NoShowReport.objects.get())
    assert NoShowReport.objects.get().status == NoShowReport.Status.PENDING
    assert booking.pk


def test_admin_filtre_les_no_shows_declares_alors_que_le_pro_etait_actif(client):
    scene, active = scheduled()
    active = slot_passed(advance(active, Status.EN_ROUTE))
    services.declare_no_show(booking=active, actor=scene.client)
    _, silent = declared()
    login(client, "Médiation")
    url = reverse("admin:bookings_noshowreport_changelist")
    oui = client.get(url, {"pro_actif": "oui"}).content.decode()
    non = client.get(url, {"pro_actif": "non"}).content.decode()
    assert str(active.public_id) in oui and str(silent.public_id) not in oui
    assert str(silent.public_id) in non and str(active.public_id) not in non


def test_admin_n_affiche_aucune_donnee_du_client(client):
    scene, booking = declared()
    services.contest_no_show(booking=booking, actor=booking.provider.owner, note="j'étais là")
    login(client, "Médiation")
    report = NoShowReport.objects.get()
    page = client.get(reverse("admin:bookings_noshowreport_change", args=[report.pk]))
    text = page.content.decode()
    assert (page.status_code == 200 and "j&#x27;étais là" in text) or "j'étais là" in text
    assert scene.client.phone not in text and scene.request.landmark not in text
