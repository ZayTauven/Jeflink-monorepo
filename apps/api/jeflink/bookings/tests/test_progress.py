"""Déroulé de l'intervention (spec 004, tâche 2) : en route, sur place, début, clôture, rappel.

Chaque action est idempotente par état : rejouée, elle répond l'état courant sans événement.
"""

from datetime import timedelta

import pytest
from django.utils import timezone

from jeflink.accounts.deletion import deletion_blockers
from jeflink.bookings import services, tasks
from jeflink.bookings.machine import Actor, Status
from jeflink.bookings.models import Booking, BookingEvent
from jeflink.common.errors import DomainError
from jeflink.notifications import events
from jeflink.providers.models import Provider
from jeflink.providers.services import set_status
from jeflink.requests.models import ServiceRequest
from jeflink.trust.models import AuditEvent

from .factories import advance, scheduled
from .test_services import expect

pytestmark = pytest.mark.django_db


def count_events(booking) -> int:
    return BookingEvent.objects.filter(booking=booking).count()


def last_event(booking) -> BookingEvent:
    return BookingEvent.objects.filter(booking=booking).latest("id")


@pytest.fixture
def notified(monkeypatch):
    """Les notifications envoyées : (type, destinataires, référence)."""
    sent = []
    monkeypatch.setattr(
        events, "notify", lambda kind, recipients, ref: sent.append((kind, list(recipients), ref))
    )
    return sent


# --- En route ----------------------------------------------------------------------------------


def test_en_route(notified):
    _, booking = scheduled()
    owner = booking.provider.owner
    result = services.mark_en_route(booking=booking, actor=owner)
    assert result.status == Status.EN_ROUTE and result.en_route_at is not None
    event = last_event(booking)
    assert (event.from_status, event.to_status, event.actor_kind) == (
        Status.SCHEDULED,
        Status.EN_ROUTE,
        Actor.PRO,
    )
    audit = AuditEvent.objects.get(action="bookings.booking.progressed")
    assert audit.metadata == {"from_status": "scheduled", "to_status": "en_route", "chained": False}
    assert (events.BOOKING_PROGRESS, [booking.client], booking.public_id) in notified


def test_rejouer_en_route_ne_cree_aucun_evenement():
    _, booking = scheduled()
    owner = booking.provider.owner
    services.mark_en_route(booking=booking, actor=owner)
    before = count_events(booking)
    again = services.mark_en_route(booking=booking, actor=owner)
    assert again.status == Status.EN_ROUTE and count_events(booking) == before
    # Même une fois sur place : l'état courant, sans événement.
    services.mark_arrived(booking=booking, actor=owner)
    before = count_events(booking)
    assert services.mark_en_route(booking=booking, actor=owner).status == Status.ON_SITE
    assert count_events(booking) == before


@pytest.mark.parametrize("status", [Status.ACCEPTED, Status.CANCELLED])
def test_en_route_refuse_hors_du_cycle(status):
    _, booking = scheduled()
    Booking.objects.filter(pk=booking.pk).update(
        status=status, cancelled_by="system" if status == Status.CANCELLED else ""
    )
    with expect("transition_not_allowed"):
        services.mark_en_route(booking=booking, actor=booking.provider.owner)


def test_autre_pro_et_pro_suspendu():
    scene, booking = scheduled(pros=2)
    with expect("not_found", 404):
        services.mark_en_route(booking=booking, actor=scene.providers[1].owner)
    Provider.objects.filter(pk=booking.provider_id).update(status="suspended")
    with expect("provider_not_verified", 403):
        services.mark_en_route(booking=booking, actor=booking.provider.owner)
    booking.refresh_from_db()
    assert booking.status == Status.SCHEDULED


# --- Sur place : rattrapage --------------------------------------------------------------------


def test_arrive_depuis_en_route():
    _, booking = scheduled()
    owner = booking.provider.owner
    services.mark_en_route(booking=booking, actor=owner)
    result = services.mark_arrived(booking=booking, actor=owner)
    assert result.status == Status.ON_SITE and result.on_site_at is not None
    assert last_event(booking).metadata == {}


def test_arrive_depuis_scheduled_rattrape_en_route_et_ecrit_deux_evenements():
    _, booking = scheduled()
    owner = booking.provider.owner
    before = count_events(booking)
    result = services.mark_arrived(booking=booking, actor=owner)
    assert result.status == Status.ON_SITE
    assert result.en_route_at is not None and result.on_site_at is not None
    first, second = BookingEvent.objects.filter(booking=booking).order_by("-id")[:2][::-1]
    assert (first.to_status, second.to_status) == (Status.EN_ROUTE, Status.ON_SITE)
    assert first.metadata == {"chained": True} and second.metadata == {"chained": True}
    assert count_events(booking) == before + 2
    audits = AuditEvent.objects.filter(action="bookings.booking.progressed")
    assert audits.count() == 2 and all(a.metadata["chained"] for a in audits)
    # Rejouée : rien de plus.
    services.mark_arrived(booking=booking, actor=owner)
    assert count_events(booking) == before + 2


def test_arrive_refuse_avant_scheduled():
    _, booking = scheduled()
    Booking.objects.filter(pk=booking.pk).update(status=Status.ACCEPTED)
    with expect("transition_not_allowed"):
        services.mark_arrived(booking=booking, actor=booking.provider.owner)


# --- Début : jamais déduit ---------------------------------------------------------------------


def test_start_exige_une_photo_ou_photos_pending():
    _, booking = scheduled()
    owner = booking.provider.owner
    services.mark_arrived(booking=booking, actor=owner)
    before = count_events(booking)
    with expect("before_photos_required", 422):
        services.start_work(booking=booking, actor=owner)
    assert count_events(booking) == before
    result = services.start_work(booking=booking, actor=owner, photos_pending=True)
    assert result.status == Status.IN_PROGRESS and result.started_at is not None
    assert last_event(booking).metadata == {"photos_pending": True}


@pytest.mark.parametrize("status", [Status.SCHEDULED, Status.EN_ROUTE])
def test_start_n_est_jamais_deduit(status):
    _, booking = scheduled()
    Booking.objects.filter(pk=booking.pk).update(status=status)
    before = count_events(booking)
    with expect("transition_not_allowed"):
        services.start_work(booking=booking, actor=booking.provider.owner, photos_pending=True)
    assert count_events(booking) == before


def test_rejouer_start_ne_cree_aucun_evenement():
    _, booking = scheduled()
    booking = advance(booking, Status.IN_PROGRESS)
    before = count_events(booking)
    again = services.start_work(booking=booking, actor=booking.provider.owner, photos_pending=True)
    assert again.status == Status.IN_PROGRESS and count_events(booking) == before


# --- occurred_at -------------------------------------------------------------------------------


def test_occurred_at_est_gardee_en_metadonnee_et_le_serveur_fait_foi():
    _, booking = scheduled()
    owner = booking.provider.owner
    device_time = timezone.now()  # après la confirmation, avant l'envoi
    result = services.mark_en_route(booking=booking, actor=owner, occurred_at=device_time)
    assert last_event(booking).metadata == {"occurred_at": device_time.isoformat()}
    assert result.en_route_at > device_time  # l'heure du serveur fait foi


@pytest.mark.parametrize(
    "delta",
    [timedelta(minutes=5), -timedelta(hours=25), -timedelta(days=3)],
    ids=["futur", "plus_de_24_h", "tres_ancien"],
)
def test_occurred_at_refusee(delta):
    _, booking = scheduled()
    before = count_events(booking)
    with expect("occurred_at_invalid", 422):
        services.mark_en_route(
            booking=booking, actor=booking.provider.owner, occurred_at=timezone.now() + delta
        )
    assert count_events(booking) == before


def test_occurred_at_avant_l_evenement_precedent_refusee():
    _, booking = scheduled()
    owner = booking.provider.owner
    services.mark_en_route(booking=booking, actor=owner)
    previous = last_event(booking).created_at
    with expect("occurred_at_invalid", 422):
        services.mark_arrived(
            booking=booking, actor=owner, occurred_at=previous - timedelta(seconds=30)
        )


# --- Annulations à partir de en_route et on_site -----------------------------------------------


def cancel(booking, *, kind, actor, reason, note=""):
    return services.cancel_booking(
        booking=booking, actor=actor, actor_kind=kind, reason=reason, note=note
    )


def test_le_client_annule_un_pro_en_route_toujours_tardif_sans_penalite():
    scene, booking = scheduled()
    booking = advance(booking, Status.EN_ROUTE)
    cancel(booking, kind=Actor.CLIENT, actor=scene.client, reason="changed_mind")
    booking.refresh_from_db()
    assert booking.status == Status.CANCELLED
    assert last_event(booking).metadata == {"late": True, "reliability_weight": 0}
    scene.request.refresh_from_db()
    assert scene.request.status == ServiceRequest.Status.CANCELLED


def test_le_pro_se_desiste_en_route_poids_2():
    scene, booking = scheduled(pros=2)
    booking = advance(booking, Status.EN_ROUTE)
    cancel(booking, kind=Actor.PRO, actor=booking.provider.owner, reason="unavailable")
    assert last_event(booking).metadata == {"late": True, "reliability_weight": 2}
    scene.request.refresh_from_db()
    assert scene.request.excluded_providers.filter(pk=booking.provider_id).exists()


def test_le_client_ne_peut_pas_annuler_un_pro_sur_place():
    scene, booking = scheduled()
    booking = advance(booking, Status.ON_SITE)
    before = count_events(booking)
    with expect("transition_not_allowed"):
        cancel(booking, kind=Actor.CLIENT, actor=scene.client, reason="changed_mind")
    assert count_events(booking) == before


@pytest.mark.parametrize(("reason", "weight"), [("job_mismatch", 2), ("client_absent", 0)])
def test_le_pro_annule_sur_place(reason, weight):
    _, booking = scheduled()
    booking = advance(booking, Status.ON_SITE)
    cancel(booking, kind=Actor.PRO, actor=booking.provider.owner, reason=reason)
    event = last_event(booking)
    assert event.reason == reason  # client_absent est tracé
    assert event.metadata == {"late": True, "reliability_weight": weight}
    audit = AuditEvent.objects.get(action="bookings.booking.cancelled")
    assert audit.metadata["from_status"] == "on_site" and audit.metadata["reason"] == reason


@pytest.mark.parametrize("status", [Status.SCHEDULED, Status.EN_ROUTE])
def test_client_absent_n_existe_que_sur_place(status):
    _, booking = scheduled()
    booking = advance(booking, Status.EN_ROUTE) if status == Status.EN_ROUTE else booking
    with expect("reason_invalid", 422):
        cancel(booking, kind=Actor.PRO, actor=booking.provider.owner, reason="client_absent")
    booking.refresh_from_db()
    assert booking.status == status


def test_le_pro_ne_peut_plus_annuler_une_intervention_en_cours():
    _, booking = scheduled()
    booking = advance(booking, Status.IN_PROGRESS)
    with expect("transition_not_allowed"):
        cancel(booking, kind=Actor.PRO, actor=booking.provider.owner, reason="unavailable")


# --- Suspension d'un pro -----------------------------------------------------------------------


def test_la_suspension_annule_jusqu_a_on_site_et_laisse_l_intervention_en_cours():
    scenes = [scheduled() for _ in range(4)]
    bookings = [b for _, b in scenes]
    provider = bookings[0].provider
    wanted = [Status.SCHEDULED, Status.EN_ROUTE, Status.ON_SITE, Status.IN_PROGRESS]
    for booking, status in zip(bookings, wanted, strict=True):
        Booking.objects.filter(pk=booking.pk).update(provider=provider, status=status)
    set_status(provider=provider, to=Provider.Status.SUSPENDED, actor=None)
    statuses = [Booking.objects.get(pk=b.pk).status for b in bookings]
    assert statuses == [Status.CANCELLED] * 3 + [Status.IN_PROGRESS]
    on_site_event = last_event(bookings[2])
    assert (on_site_event.actor_kind, on_site_event.reason) == ("system", "provider_suspended")
    assert on_site_event.metadata["reliability_weight"] == 0


def test_un_pro_suspendu_ne_progresse_plus():
    _, booking = scheduled()
    booking = advance(booking, Status.ON_SITE)
    Provider.objects.filter(pk=booking.provider_id).update(status="suspended")
    with expect("provider_not_verified", 403):
        services.start_work(booking=booking, actor=booking.provider.owner, photos_pending=True)


# --- Suppression du compte ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("status", "blocks"),
    [
        (Status.EN_ROUTE, True),
        (Status.ON_SITE, True),
        (Status.IN_PROGRESS, True),
        (Status.COMPLETED, True),
        (Status.DISPUTED, True),
        (Status.CLOSED, False),
        (Status.CANCELLED, False),
    ],
)
def test_une_reservation_engagee_bloque_la_suppression(status, blocks):
    scene, booking = scheduled()
    Booking.objects.filter(pk=booking.pk).update(
        status=status, cancelled_by="system" if status == Status.CANCELLED else ""
    )
    reasons = deletion_blockers(scene.client)
    assert ("deletion_blocked_active_booking" in reasons) is blocks
    assert (
        "deletion_blocked_active_booking" in deletion_blockers(booking.provider.owner)
    ) is blocks


# --- Clôture -----------------------------------------------------------------------------------


@pytest.fixture
def close_handler():
    calls = []

    def handler(booking, reason):
        calls.append((booking.public_id, booking.status, reason))

    services.register_close_handler(handler)
    yield calls
    services._CLOSE_HANDLERS.remove(handler)


def completed_booking(*, deadline_in: timedelta):
    _, booking = scheduled()
    booking = advance(booking, Status.COMPLETED)
    Booking.objects.filter(pk=booking.pk).update(dispute_deadline=timezone.now() + deadline_in)
    booking.refresh_from_db()
    return booking


def test_completed_pose_les_horodatages_et_la_fenetre_de_contestation():
    _, booking = scheduled()
    booking = advance(booking, Status.COMPLETED)
    assert booking.completed_at is not None
    assert booking.dispute_deadline - booking.completed_at == timedelta(hours=48)


def test_close_due_cloture_les_echues_et_appelle_les_gestionnaires_une_fois(
    close_handler, notified
):
    due = completed_booking(deadline_in=-timedelta(minutes=1))
    waiting = completed_booking(deadline_in=timedelta(hours=1))
    assert services.close_due() == 1
    due.refresh_from_db()
    waiting.refresh_from_db()
    assert (due.status, due.closed_at is not None) == (Status.CLOSED, True)
    assert waiting.status == Status.COMPLETED
    event = last_event(due)
    assert (event.from_status, event.to_status, event.actor_kind, event.reason) == (
        Status.COMPLETED,
        Status.CLOSED,
        "system",
        "window_elapsed",
    )
    assert close_handler == [(due.public_id, Status.CLOSED, "window_elapsed")]
    assert services.close_due() == 0  # idempotente
    assert len(close_handler) == 1
    assert AuditEvent.objects.get(action="bookings.booking.closed").metadata == {
        "reason": "window_elapsed"
    }
    assert any(kind == events.BOOKING_CLOSED for kind, *_ in notified)


def test_close_due_ne_cloture_pas_une_reservation_contestee(close_handler):
    booking = completed_booking(deadline_in=-timedelta(minutes=1))
    Booking.objects.filter(pk=booking.pk).update(status=Status.DISPUTED)
    assert services.close_due() == 0 and close_handler == []


def test_close_due_par_la_tache():
    booking = completed_booking(deadline_in=-timedelta(minutes=1))
    assert tasks.close_due() == 1
    booking.refresh_from_db()
    assert booking.status == Status.CLOSED


def test_un_gestionnaire_qui_echoue_annule_la_cloture(close_handler):
    def broken(booking, reason):
        raise RuntimeError("boom")

    services.register_close_handler(broken)
    try:
        booking = completed_booking(deadline_in=-timedelta(minutes=1))
        with pytest.raises(RuntimeError):
            services.close_due()
        booking.refresh_from_db()
        assert booking.status == Status.COMPLETED
    finally:
        services._CLOSE_HANDLERS.remove(broken)


def test_enregistrer_deux_fois_le_meme_gestionnaire_ne_l_appelle_qu_une_fois(close_handler):
    handler = services._CLOSE_HANDLERS[-1]
    services.register_close_handler(handler)
    completed_booking(deadline_in=-timedelta(minutes=1))
    services.close_due()
    assert len(close_handler) == 1


# --- Rappel de contestation --------------------------------------------------------------------


def test_le_rappel_part_une_seule_fois_dans_les_12_dernieres_heures(notified):
    soon = completed_booking(deadline_in=timedelta(hours=11))
    far = completed_booking(deadline_in=timedelta(hours=30))
    assert services.remind_disputes() == 1
    soon.refresh_from_db()
    far.refresh_from_db()
    assert soon.dispute_reminder_sent_at is not None and far.dispute_reminder_sent_at is None
    assert (events.DISPUTE_REMINDER, [soon.client], soon.public_id) in notified
    assert services.remind_disputes() == 0  # une seule fois
    assert len([n for n in notified if n[0] == events.DISPUTE_REMINDER]) == 1


def test_pas_de_rappel_apres_l_echeance_ni_pour_une_reservation_cloturee(notified):
    completed_booking(deadline_in=-timedelta(minutes=5))
    notified.clear()
    assert services.remind_disputes() == 0 and notified == []


def test_rappel_par_la_tache():
    completed_booking(deadline_in=timedelta(hours=2))
    assert tasks.remind_disputes() == 1


def test_une_erreur_de_domaine_reste_une_erreur_de_domaine():
    _, booking = scheduled()
    with pytest.raises(DomainError):
        services.transition(
            booking, to=Status.CLOSED, actor=None, actor_kind=Actor.SYSTEM, reason="x"
        )
