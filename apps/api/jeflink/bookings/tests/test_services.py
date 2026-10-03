from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import timedelta

import pytest
from django.db import connection
from django.utils import timezone

from jeflink.accounts.deletion import deletion_blockers
from jeflink.accounts.models import User
from jeflink.bookings import services, tasks
from jeflink.bookings.machine import Actor, Status
from jeflink.bookings.models import Booking, BookingEvent
from jeflink.bookings.selectors import (
    active_booking_for_request,
    booking_for_client,
    booking_for_provider,
    bookings_for_client,
    bookings_for_provider,
)
from jeflink.common.errors import DomainError
from jeflink.providers.models import Provider
from jeflink.providers.services import set_status
from jeflink.requests import services as request_services
from jeflink.requests.models import Quote, ServiceRequest
from jeflink.requests.tests.factories import ServiceRequestFactory
from jeflink.trust.models import AuditEvent

from .factories import accept, confirm, make_scene

pytestmark = pytest.mark.django_db
RStatus = ServiceRequest.Status
QStatus = Quote.Status


def refresh(*objects):
    for obj in objects:
        obj.refresh_from_db()


@contextmanager
def expect(code, status=409):
    with pytest.raises(DomainError) as exc:
        yield
    assert (exc.value.code, exc.value.status_code) == (code, status)


def make_overdue(booking: Booking) -> None:
    Booking.objects.filter(pk=booking.pk).update(
        confirm_deadline=timezone.now() - timedelta(minutes=1)
    )


# --- Acceptation -------------------------------------------------------------------------------


def test_accepter_un_devis_cree_la_reservation(django_capture_on_commit_callbacks):
    scene = make_scene(pros=3)
    booking = accept(scene, 1)
    refresh(booking, scene.request, *scene.quotes)
    assert booking.status == Status.ACCEPTED and booking.client == scene.client
    assert booking.provider == scene.providers[1]
    assert booking.amount_xof == scene.quotes[1].total_xof
    assert (booking.slot_start, booking.slot_end) == (
        scene.quotes[1].slot_start,
        scene.quotes[1].slot_end,
    )
    assert scene.request.status == RStatus.BOOKED
    assert [q.status for q in scene.quotes] == [QStatus.HELD, QStatus.ACCEPTED, QStatus.HELD]
    assert booking.confirm_deadline > timezone.now()
    event = BookingEvent.objects.get(booking=booking)
    assert (event.from_status, event.to_status) == ("", Status.ACCEPTED)
    assert (event.actor_kind, event.reason) == (Actor.CLIENT, "quote_accepted")
    audit = AuditEvent.objects.get(action="bookings.booking.created")
    assert audit.metadata == {"urgent": False}


def test_delai_de_confirmation_urgent_plus_court(settings):
    settings.BOOKING_CONFIRM_QUIET_HOURS = (0, 0)  # pas de gel : le test ne dépend pas de l'heure
    urgent = accept(make_scene(pros=1, urgent=True))
    normal = accept(make_scene(pros=1))
    assert timedelta(minutes=55) < urgent.confirm_deadline - timezone.now() <= timedelta(hours=1)
    assert timedelta(hours=3, minutes=55) < normal.confirm_deadline - timezone.now()


def test_rejouer_l_acceptation_rend_la_meme_reservation():
    scene = make_scene()
    first = services.create_from_quote(quote=scene.quotes[0], actor=scene.client)
    again = services.create_from_quote(quote=scene.quotes[0], actor=scene.client)
    assert first.created and not again.created and first.booking.pk == again.booking.pk
    assert Booking.objects.count() == 1 and BookingEvent.objects.count() == 1


def test_le_devis_d_un_autre_client_est_un_404(complete_user_factory):
    scene = make_scene()
    with expect("not_found", 404):
        services.create_from_quote(quote=scene.quotes[0], actor=complete_user_factory())
    assert not Booking.objects.exists()


def test_un_deuxieme_devis_apres_acceptation_est_refuse():
    scene = make_scene()
    accept(scene, 0)
    with expect("quote_not_available"):
        services.create_from_quote(quote=scene.quotes[1], actor=scene.client)
    assert Booking.objects.count() == 1


@pytest.mark.parametrize(
    "mutate",
    [
        lambda s: Quote.objects.filter(pk=s.quotes[0].pk).update(
            valid_until=timezone.now() - timedelta(minutes=1)
        ),
        lambda s: Quote.objects.filter(pk=s.quotes[0].pk).update(status=QStatus.WITHDRAWN),
        lambda s: Quote.objects.filter(pk=s.quotes[0].pk).update(
            slot_start=timezone.now() - timedelta(hours=2),
            slot_end=timezone.now() - timedelta(hours=1),
        ),
        lambda s: ServiceRequest.objects.filter(pk=s.request.pk).update(
            expires_at=timezone.now() - timedelta(minutes=1)
        ),
        lambda s: ServiceRequest.objects.filter(pk=s.request.pk).update(status=RStatus.CANCELLED),
    ],
    ids=["devis_echu", "devis_retire", "creneau_passe", "demande_echue", "demande_annulee"],
)
def test_devis_indisponible(mutate):
    scene = make_scene()
    mutate(scene)
    with expect("quote_not_available"):
        services.create_from_quote(quote=scene.quotes[0], actor=scene.client)
    assert not Booking.objects.exists()


def test_pro_suspendu_entre_le_devis_et_le_choix(user_factory):
    scene = make_scene()
    Provider.objects.filter(pk=scene.providers[0].pk).update(status="suspended")
    with expect("quote_not_available"):
        services.create_from_quote(quote=scene.quotes[0], actor=scene.client)


def test_compte_desactive_refuse():
    scene = make_scene()
    User.objects.filter(pk=scene.client.pk).update(is_active=False, deactivation_reason="ops_other")
    with expect("account_disabled", 403):
        services.create_from_quote(quote=scene.quotes[0], actor=scene.client)


@pytest.mark.django_db(transaction=True, databases="__all__", serialized_rollback=True)
def test_deux_acceptations_simultanees_une_seule_reservation():
    scene = make_scene(pros=2)

    def attempt(index):
        try:
            return services.create_from_quote(quote=scene.quotes[index], actor=scene.client).created
        except DomainError as exc:
            return exc.code
        finally:
            connection.close()

    # Deux fois le même devis : la première crée, la seconde rejoue.
    with ThreadPoolExecutor(2) as pool:
        same = sorted(map(str, pool.map(attempt, [0, 0])))
    assert same == ["False", "True"]
    assert Booking.objects.count() == 1


@pytest.mark.django_db(transaction=True, databases="__all__", serialized_rollback=True)
def test_deux_devis_differents_en_meme_temps_un_seul_gagne():
    scene = make_scene(pros=2)

    def attempt(index):
        try:
            return services.create_from_quote(quote=scene.quotes[index], actor=scene.client).created
        except DomainError as exc:
            return exc.code
        finally:
            connection.close()

    with ThreadPoolExecutor(2) as pool:
        results = sorted(map(str, pool.map(attempt, [0, 1])))
    assert results == ["True", "quote_not_available"]
    assert Booking.objects.exclude(status=Status.CANCELLED).count() == 1


# --- Confirmation par le pro -------------------------------------------------------------------


def test_le_pro_confirme_la_reservation():
    scene = make_scene(pros=3)
    booking = accept(scene, 0)
    confirmed = confirm(booking)
    refresh(scene.request, *scene.quotes)
    assert confirmed.status == Status.SCHEDULED
    assert [q.status for q in scene.quotes] == [
        QStatus.ACCEPTED,
        QStatus.DECLINED,
        QStatus.DECLINED,
    ]
    assert scene.request.status == RStatus.BOOKED
    event = BookingEvent.objects.filter(booking=booking).latest("id")
    assert (event.from_status, event.to_status, event.actor_kind) == (
        Status.ACCEPTED,
        Status.SCHEDULED,
        Actor.PRO,
    )
    assert AuditEvent.objects.filter(action="bookings.booking.confirmed").count() == 1


def test_confirmation_par_un_autre_pro_ou_un_pro_non_verifie():
    scene = make_scene(pros=2)
    booking = accept(scene, 0)
    with expect("not_found", 404):
        services.confirm_booking(booking=booking, actor=scene.providers[1].owner)
    Provider.objects.filter(pk=scene.providers[0].pk).update(status="suspended")
    with expect("provider_not_verified", 403):
        services.confirm_booking(booking=booking, actor=scene.providers[0].owner)
    booking.refresh_from_db()
    assert booking.status == Status.ACCEPTED


def test_confirmer_deux_fois_refuse():
    scene = make_scene()
    booking = accept(scene)
    confirm(booking)
    with expect("transition_not_allowed"):
        confirm(booking)


def test_confirmation_apres_l_echeance_annule_au_lieu_de_ressusciter():
    scene = make_scene(pros=2)
    booking = accept(scene, 0)
    make_overdue(booking)
    with expect("transition_not_allowed"):
        confirm(booking)
    refresh(booking, scene.request)
    assert booking.status == Status.CANCELLED and booking.cancel_reason == "pro_unconfirmed"
    assert scene.request.status == RStatus.QUOTED


# --- Annulation par le client ------------------------------------------------------------------


@pytest.mark.parametrize("confirmed", [False, True])
def test_le_client_annule_sa_reservation(confirmed):
    scene = make_scene(pros=2)
    booking = accept(scene, 0)
    if confirmed:
        confirm(booking)
    cancelled = services.cancel_booking(
        booking=booking, actor=scene.client, actor_kind=Actor.CLIENT, reason="found_other"
    )
    refresh(scene.request, *scene.quotes)
    assert cancelled.status == Status.CANCELLED
    assert (cancelled.cancelled_by, cancelled.cancel_reason) == ("client", "found_other")
    assert scene.request.status == RStatus.CANCELLED
    assert scene.quotes[1].status == QStatus.DECLINED
    event = BookingEvent.objects.filter(booking=booking).latest("id")
    assert event.metadata == {"late": False, "reliability_weight": 0}


def test_annulation_tardive_du_client_tracee_sans_penalite():
    scene = make_scene()
    booking = accept(scene)
    confirm(booking)
    Booking.objects.filter(pk=booking.pk).update(
        slot_start=timezone.now() + timedelta(minutes=30),
        slot_end=timezone.now() + timedelta(hours=2),
    )
    services.cancel_booking(
        booking=booking, actor=scene.client, actor_kind=Actor.CLIENT, reason="price"
    )
    event = BookingEvent.objects.filter(booking=booking).latest("id")
    assert event.metadata == {"late": True, "reliability_weight": 0}  # tracé, jamais contre le pro


def test_annulation_par_un_autre_compte_ou_motif_invalide(complete_user_factory):
    scene = make_scene()
    booking = accept(scene)
    with expect("not_found", 404):
        services.cancel_booking(
            booking=booking, actor=complete_user_factory(), actor_kind=Actor.CLIENT,
            reason="price",
        )  # fmt: skip
    for reason, note, code in [("too_far", "", "reason_invalid"), ("other", "", "note_invalid")]:
        with expect(code, 422):
            services.cancel_booking(
                booking=booking, actor=scene.client, actor_kind=Actor.CLIENT, reason=reason,
                note=note,
            )  # fmt: skip
    booking.refresh_from_db()
    assert booking.status == Status.ACCEPTED


def test_annulation_refusee_hors_accepted_ou_scheduled():
    scene = make_scene()
    booking = accept(scene)
    services.cancel_booking(
        booking=booking, actor=scene.client, actor_kind=Actor.CLIENT, reason="price"
    )
    with expect("transition_not_allowed"):
        services.cancel_booking(
            booking=booking, actor=scene.client, actor_kind=Actor.CLIENT, reason="price"
        )


def test_la_note_est_gardee_dans_l_evenement_mais_pas_dans_l_audit():
    scene = make_scene()
    booking = accept(scene)
    services.cancel_booking(
        booking=booking, actor=scene.client, actor_kind=Actor.CLIENT, reason="other",
        note="Mon voisin m'a trouvé quelqu'un",
    )  # fmt: skip
    assert BookingEvent.objects.filter(booking=booking).latest("id").note.startswith("Mon voisin")
    assert "voisin" not in str([e.metadata for e in AuditEvent.objects.all()])


# --- Désistement du pro ------------------------------------------------------------------------


def test_desistement_avant_confirmation_sans_poids_et_les_autres_devis_reviennent():
    scene = make_scene(pros=3)
    booking = accept(scene, 0)
    services.cancel_booking(
        booking=booking, actor=scene.providers[0].owner, actor_kind=Actor.PRO, reason="unavailable"
    )
    refresh(booking, scene.request, *scene.quotes)
    assert booking.status == Status.CANCELLED and booking.cancelled_by == "pro"
    assert [q.status for q in scene.quotes] == [
        QStatus.WITHDRAWN,
        QStatus.SUBMITTED,
        QStatus.SUBMITTED,
    ]
    assert scene.request.status == RStatus.QUOTED
    assert list(scene.request.excluded_providers.all()) == [scene.providers[0]]
    event = BookingEvent.objects.filter(booking=booking).latest("id")
    assert event.metadata == {"late": False, "reliability_weight": 0}
    # Le client peut accepter un autre devis.
    assert services.create_from_quote(quote=scene.quotes[1], actor=scene.client).created


def test_desistement_apres_confirmation_compte_1_ou_2_si_tardif():
    scene = make_scene(pros=1)
    booking = accept(scene)
    confirm(booking)
    services.cancel_booking(
        booking=booking, actor=scene.providers[0].owner, actor_kind=Actor.PRO, reason="too_far"
    )
    refresh(scene.request)
    event = BookingEvent.objects.filter(booking=booking).latest("id")
    assert event.metadata == {"late": False, "reliability_weight": 1}
    assert scene.request.status == RStatus.OPEN  # plus aucun devis : demande rouverte
    assert timedelta(hours=70) < scene.request.expires_at - timezone.now()  # nouvelle échéance

    late = make_scene(pros=1)
    other = accept(late)
    confirm(other)
    Booking.objects.filter(pk=other.pk).update(
        slot_start=timezone.now() + timedelta(minutes=30),
        slot_end=timezone.now() + timedelta(hours=2),
    )
    services.cancel_booking(
        booking=other, actor=late.providers[0].owner, actor_kind=Actor.PRO, reason="unavailable"
    )
    assert BookingEvent.objects.filter(booking=other).latest("id").metadata == {
        "late": True,
        "reliability_weight": 2,
    }


def test_le_pro_exclu_ne_revoit_plus_la_demande():
    from jeflink.requests.selectors import requests_for_provider

    scene = make_scene(pros=2)
    booking = accept(scene, 0)
    services.cancel_booking(
        booking=booking, actor=scene.providers[0].owner, actor_kind=Actor.PRO, reason="other",
        note="Je suis malade",
    )  # fmt: skip
    assert not requests_for_provider(provider=scene.providers[0]).exists()


def test_un_pro_ne_peut_pas_annuler_celle_d_un_autre_ni_suspendu():
    scene = make_scene(pros=2)
    booking = accept(scene, 0)
    with expect("not_found", 404):
        services.cancel_booking(
            booking=booking, actor=scene.providers[1].owner, actor_kind=Actor.PRO, reason="other",
            note="x",
        )  # fmt: skip
    Provider.objects.filter(pk=scene.providers[0].pk).update(status="suspended")
    with expect("provider_not_verified", 403):
        services.cancel_booking(
            booking=booking, actor=scene.providers[0].owner, actor_kind=Actor.PRO,
            reason="unavailable",
        )  # fmt: skip


def test_acteur_non_autorise_a_annuler():
    scene = make_scene()
    booking = accept(scene)
    for kind in (Actor.SYSTEM, Actor.OPS):
        with expect("transition_not_allowed"):
            services.cancel_booking(
                booking=booking, actor=scene.client, actor_kind=kind, reason="price"
            )


# --- Non-confirmation (tâche) ------------------------------------------------------------------


def test_cancel_unconfirmed_annule_remet_les_devis_et_exclut_le_pro():
    scene = make_scene(pros=3)
    booking = accept(scene, 0)
    make_overdue(booking)
    assert services.cancel_unconfirmed() == 1
    refresh(booking, scene.request, *scene.quotes)
    assert booking.status == Status.CANCELLED
    assert (booking.cancelled_by, booking.cancel_reason) == ("system", "pro_unconfirmed")
    assert [q.status for q in scene.quotes] == [
        QStatus.WITHDRAWN,
        QStatus.SUBMITTED,
        QStatus.SUBMITTED,
    ]
    assert scene.request.status == RStatus.QUOTED
    assert scene.providers[0] in scene.request.excluded_providers.all()
    event = BookingEvent.objects.filter(booking=booking).latest("id")
    assert (event.actor, event.actor_kind) == (None, Actor.SYSTEM)
    assert event.metadata == {"late": False, "reliability_weight": 0}  # poids 0 en V1
    assert services.cancel_unconfirmed() == 0  # idempotent


def test_cancel_unconfirmed_ne_touche_ni_les_reservations_en_cours_ni_les_confirmees():
    waiting = accept(make_scene())
    confirmed = confirm(accept(make_scene()))
    make_overdue(confirmed)  # l'échéance passée ne compte plus une fois confirmée
    assert services.cancel_unconfirmed() == 0
    waiting.refresh_from_db()
    confirmed.refresh_from_db()
    assert waiting.status == Status.ACCEPTED and confirmed.status == Status.SCHEDULED


def test_cancel_unconfirmed_via_la_tache():
    booking = accept(make_scene())
    make_overdue(booking)
    assert tasks.cancel_unconfirmed() == 1


def test_sans_autre_devis_valide_la_demande_rouverte():
    scene = make_scene(pros=2)
    booking = accept(scene, 0)
    Quote.objects.filter(pk=scene.quotes[1].pk).update(
        valid_until=timezone.now() - timedelta(minutes=1)
    )
    make_overdue(booking)
    services.cancel_unconfirmed()
    refresh(scene.request, scene.quotes[1])
    assert scene.quotes[1].status == QStatus.EXPIRED
    assert scene.request.status == RStatus.OPEN


# --- Suspension du pro -------------------------------------------------------------------------


def test_suspension_annule_les_reservations_et_retire_les_devis():
    scene = make_scene(pros=2)
    waiting = accept(scene, 0)
    other = make_scene(pros=1)
    other_booking = accept(other)
    confirm(other_booking)
    # Même pro, deuxième réservation confirmée.
    Booking.objects.filter(pk=other_booking.pk).update(provider=scene.providers[0])
    set_status(provider=scene.providers[0], to=Provider.Status.SUSPENDED, actor=scene.client)
    refresh(waiting, other_booking, scene.request, other.request)
    for booking in (waiting, other_booking):
        assert (booking.status, booking.cancelled_by, booking.cancel_reason) == (
            Status.CANCELLED,
            "system",
            "provider_suspended",
        )
    assert BookingEvent.objects.filter(booking=other_booking).latest("id").metadata == {
        "late": False,
        "reliability_weight": 0,
    }
    assert scene.request.status == RStatus.QUOTED  # le devis du 2e pro revient


# --- Suppression du compte ---------------------------------------------------------------------


@pytest.mark.parametrize("confirmed", [False, True])
def test_reservation_en_cours_bloque_la_suppression_des_deux_comptes(confirmed):
    scene = make_scene(pros=1)
    booking = accept(scene)
    if confirmed:
        confirm(booking)
    assert "deletion_blocked_active_booking" in deletion_blockers(scene.client)
    assert "deletion_blocked_active_booking" in deletion_blockers(scene.providers[0].owner)


def test_reservation_annulee_ne_bloque_plus():
    scene = make_scene(pros=1)
    booking = accept(scene)
    services.cancel_booking(
        booking=booking, actor=scene.client, actor_kind=Actor.CLIENT, reason="price"
    )
    assert "deletion_blocked_active_booking" not in deletion_blockers(scene.client)
    assert "deletion_blocked_active_booking" not in deletion_blockers(scene.providers[0].owner)


def test_anonymiseur_efface_les_notes_des_evenements():
    from jeflink.accounts.deletion import _anonymize

    scene = make_scene(pros=1)
    booking = accept(scene)
    services.cancel_booking(
        booking=booking, actor=scene.client, actor_kind=Actor.CLIENT, reason="other",
        note="Une note libre",
    )  # fmt: skip
    _anonymize(scene.client, reason="user_request")
    assert BookingEvent.objects.filter(booking=booking).exclude(note="").count() == 0
    assert BookingEvent.objects.filter(booking=booking).count() == 2  # le journal reste


def test_purge_garde_le_repere_d_une_demande_qui_a_eu_une_reservation():
    scene = make_scene(pros=1)
    booking = accept(scene)
    services.cancel_booking(
        booking=booking, actor=scene.client, actor_kind=Actor.CLIENT, reason="price"
    )
    ServiceRequest.objects.filter(pk=scene.request.pk).update(
        closed_at=timezone.now() - timedelta(days=40)
    )
    lonely = ServiceRequestFactory(
        status=RStatus.CANCELLED, closed_at=timezone.now() - timedelta(days=40)
    )
    assert request_services.purge_locations() == 1
    refresh(scene.request, lonely)
    assert scene.request.landmark and lonely.landmark == ""


# --- Sélecteurs --------------------------------------------------------------------------------


def test_selecteurs_filtrent_par_proprietaire(complete_user_factory):
    scene = make_scene(pros=2)
    booking = accept(scene, 0)
    assert list(bookings_for_client(user=scene.client)) == [booking]
    assert list(bookings_for_provider(provider=scene.providers[0])) == [booking]
    assert not bookings_for_provider(provider=scene.providers[1]).exists()
    with expect("not_found", 404):
        booking_for_client(user=complete_user_factory(), public_id=booking.public_id)
    with expect("not_found", 404):
        booking_for_provider(provider=scene.providers[1], public_id=booking.public_id)


def test_une_reservation_echue_n_est_plus_montree_meme_sans_la_tache():
    scene = make_scene()
    booking = accept(scene)
    assert active_booking_for_request(scene.request) == booking
    make_overdue(booking)
    assert active_booking_for_request(scene.request) is None
    assert not bookings_for_client(user=scene.client).exists()
    assert not bookings_for_provider(provider=scene.providers[0]).exists()


def test_la_pro_suspendu_lit_encore_ses_reservations():
    scene = make_scene()
    booking = accept(scene)
    Provider.objects.filter(pk=scene.providers[0].pk).update(status="suspended")
    provider = Provider.objects.get(pk=scene.providers[0].pk)
    assert list(bookings_for_provider(provider=provider)) == [booking]
