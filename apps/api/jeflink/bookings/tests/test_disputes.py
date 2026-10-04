"""Litiges (spec 004, tâche 7) : ouverture avant l'échéance, décision de l'Ops, effets de
``for_client``, photos de l'admin auditées, anonymiseur, API."""

from datetime import timedelta

import pytest
from django.contrib.auth.models import Group
from django.urls import reverse
from django.utils import timezone

from jeflink.accounts.models import User
from jeflink.accounts.tests.factories import CompleteUserFactory
from jeflink.bookings import services
from jeflink.bookings.machine import Status
from jeflink.bookings.models import Booking, BookingEvent, BookingPhoto
from jeflink.common import storage
from jeflink.common.tests.test_images import jpeg_with_gps
from jeflink.notifications import events
from jeflink.requests.tests.test_requests_api import bearer
from jeflink.trust.models import AuditEvent, Dispute
from jeflink.trust.services import anonymize_disputes

from .factories import advance, scheduled
from .test_services import expect

pytestmark = pytest.mark.django_db
TEXT = "Le joint fuit encore, le travail n'a pas été terminé."


@pytest.fixture(autouse=True)
def _second_facteur_valide(monkeypatch):
    monkeypatch.setattr("jeflink.accounts.admin_site.admin_mfa_valid", lambda request: True)


@pytest.fixture
def notified(monkeypatch):
    sent = []
    monkeypatch.setattr(
        events, "notify", lambda kind, recipients, ref: sent.append((kind, list(recipients), ref))
    )
    return sent


def completed():
    scene, booking = scheduled()
    return scene, advance(booking, Status.COMPLETED)


def disputed(reason="poor_quality"):
    scene, booking = completed()
    services.open_dispute(booking=booking, actor=scene.client, reason=reason, description=TEXT)
    booking.refresh_from_db()
    return scene, booking


def ops_user(group="Médiation", phone="+221770000901"):
    user = User.objects.create_user(phone, is_staff=True)
    user.groups.add(Group.objects.get(name=group))
    return user


# --- Ouverture ---------------------------------------------------------------------------------


def test_le_client_ouvre_un_litige(notified):
    scene, booking = completed()
    result = services.open_dispute(
        booking=booking, actor=scene.client, reason="damage", description=f"  {TEXT}  "
    )
    assert result.status == Status.DISPUTED
    dispute = Dispute.objects.get(booking=booking)
    assert (dispute.reason, dispute.status, dispute.decision) == ("damage", "open", "")
    assert dispute.description == TEXT  # espaces normalisés
    event = BookingEvent.objects.filter(booking=booking).latest("id")
    assert (event.from_status, event.to_status, event.actor_kind, event.reason) == (
        "completed",
        "disputed",
        "client",
        "dispute_opened",
    )
    audit = AuditEvent.objects.get(action="bookings.booking.disputed")
    assert audit.metadata == {"reason": "damage"} and "joint" not in str(audit.metadata)
    assert (events.BOOKING_DISPUTED, [booking.provider.owner], booking.public_id) in notified


def test_ouverture_rejouee_ne_cree_ni_second_litige_ni_evenement():
    scene, booking = disputed()
    before = BookingEvent.objects.filter(booking=booking).count()
    services.open_dispute(booking=booking, actor=scene.client, reason="price", description=TEXT)
    assert (
        Dispute.objects.count() == 1
        and BookingEvent.objects.filter(booking=booking).count() == before
    )


def test_litige_refuse_apres_l_echeance_ou_la_cloture():
    scene, booking = completed()
    Booking.objects.filter(pk=booking.pk).update(
        dispute_deadline=timezone.now() - timedelta(minutes=1)
    )
    with expect("dispute_window_closed"):
        services.open_dispute(
            booking=booking, actor=scene.client, reason="damage", description=TEXT
        )
    Booking.objects.filter(pk=booking.pk).update(status=Status.CLOSED)
    with expect("dispute_window_closed"):
        services.open_dispute(
            booking=booking, actor=scene.client, reason="damage", description=TEXT
        )
    assert not Dispute.objects.exists()


@pytest.mark.parametrize("status", [Status.SCHEDULED, Status.EN_ROUTE, Status.IN_PROGRESS])
def test_litige_refuse_avant_la_fin_du_travail(status):
    scene, booking = scheduled()
    Booking.objects.filter(pk=booking.pk).update(status=status)
    with expect("transition_not_allowed"):
        services.open_dispute(
            booking=booking, actor=scene.client, reason="damage", description=TEXT
        )


@pytest.mark.parametrize(
    ("reason", "description", "code"),
    [
        ("gourmandise", TEXT, "reason_invalid"),
        ("damage", "court", "description_invalid"),
        ("damage", "x" * 1001, "description_invalid"),
        ("damage", "   ", "description_invalid"),
    ],
)
def test_motif_et_texte_valides(reason, description, code):
    scene, booking = completed()
    with expect(code, 422):
        services.open_dispute(
            booking=booking, actor=scene.client, reason=reason, description=description
        )
    booking.refresh_from_db()
    assert booking.status == Status.COMPLETED and not Dispute.objects.exists()


def test_litige_refuse_a_un_autre_compte_et_au_pro():
    scene, booking = completed()
    with expect("not_found", 404):
        services.open_dispute(
            booking=booking, actor=CompleteUserFactory(), reason="damage", description=TEXT
        )
    with expect("not_found", 404):
        services.open_dispute(
            booking=booking, actor=booking.provider.owner, reason="damage", description=TEXT
        )
    assert scene.client


def test_un_litige_ouvert_n_est_pas_cloture_par_la_fenetre():
    _, booking = disputed()
    Booking.objects.filter(pk=booking.pk).update(
        dispute_deadline=timezone.now() - timedelta(hours=1)
    )
    assert services.close_due() == 0
    booking.refresh_from_db()
    assert booking.status == Status.DISPUTED


# --- Décision ----------------------------------------------------------------------------------


@pytest.fixture
def close_handler():
    calls = []
    services.register_close_handler(lambda booking, reason: calls.append((booking.status, reason)))
    handler = services._CLOSE_HANDLERS[-1]
    yield calls
    services._CLOSE_HANDLERS.remove(handler)


@pytest.mark.parametrize(
    ("decision", "weight"), [("for_client", 2), ("for_pro", 0), ("no_fault", 0)]
)
def test_l_ops_tranche_et_cloture(decision, weight, close_handler, notified):
    scene, booking = disputed()
    ops = ops_user()
    result = services.resolve_dispute(
        dispute=Dispute.objects.get(),
        decision=decision,
        note="Client joint par téléphone",
        operator=ops,
    )
    assert result.status == Status.CLOSED and result.closed_at
    dispute = Dispute.objects.get()
    assert (dispute.status, dispute.decision, dispute.resolved_by) == ("resolved", decision, ops)
    assert dispute.decision_note == "Client joint par téléphone" and dispute.resolved_at
    event = BookingEvent.objects.filter(booking=booking).latest("id")
    assert (event.from_status, event.to_status, event.actor_kind, event.actor) == (
        "disputed",
        "closed",
        "ops",
        ops,
    )
    assert event.reason == f"dispute_{decision}"
    assert event.metadata == {"dispute_decision": decision, "reliability_weight": weight}
    audit = AuditEvent.objects.get(action="bookings.dispute.decided")
    assert audit.actor_kind == "ops" and audit.actor == ops
    assert audit.metadata == {"decision": decision, "reliability_weight": weight}
    assert "téléphone" not in str(audit.metadata)
    assert close_handler == [("closed", f"dispute_{decision}")]  # appelé une seule fois
    recipients = [n for n in notified if n[0] == events.DISPUTE_DECIDED]
    assert recipients == [
        (events.DISPUTE_DECIDED, [booking.provider.owner, scene.client], booking.public_id)
    ]


def test_decision_deja_prise_inconnue_ou_sans_note():
    _, booking = disputed()
    dispute = Dispute.objects.get()
    ops = ops_user()
    with expect("decision_invalid", 422):
        services.resolve_dispute(dispute=dispute, decision="remboursement", note="x", operator=ops)
    with expect("note_invalid", 422):
        services.resolve_dispute(dispute=dispute, decision="for_pro", note="  ", operator=ops)
    booking.refresh_from_db()
    assert booking.status == Status.DISPUTED  # la décision invalide n'a rien clos
    services.resolve_dispute(dispute=dispute, decision="for_pro", note="ok", operator=ops)
    with expect("transition_not_allowed"):
        services.resolve_dispute(dispute=dispute, decision="for_client", note="ok", operator=ops)


# --- Anonymiseur -------------------------------------------------------------------------------


def test_l_anonymiseur_efface_le_texte_du_client():
    scene, _ = disputed()
    anonymize_disputes(scene.client)
    assert Dispute.objects.get().description == ""


def test_l_anonymiseur_est_enregistre():
    from jeflink.accounts.deletion import _ANONYMIZERS

    assert "trust" in _ANONYMIZERS


# --- Admin « Médiation » -----------------------------------------------------------------------


def test_admin_trancher_un_litige(client):
    _, booking = disputed()
    ops = ops_user()
    client.force_login(ops)
    url = reverse("admin:trust_dispute_changelist")
    dispute = Dispute.objects.get()
    response = client.post(url, {"action": "resolve", "_selected_action": [dispute.pk]})
    assert response.status_code == 200 and "Joignez le client" in response.content.decode()
    response = client.post(
        url,
        {
            "action": "resolve",
            "_selected_action": [dispute.pk],
            "apply": "1",
            "decision": "for_client",
            "note": "Photos concordantes",
        },
        follow=True,
    )
    assert response.status_code == 200
    booking.refresh_from_db()
    dispute.refresh_from_db()
    assert booking.status == Status.CLOSED and dispute.decision == "for_client"
    assert AuditEvent.objects.filter(action="bookings.dispute.decided", actor=ops).count() == 1


def test_admin_un_autre_groupe_ne_voit_ni_ne_tranche(client):
    disputed()
    client.force_login(ops_user("Validation pros", "+221770000902"))
    url = reverse("admin:trust_dispute_changelist")
    assert client.get(url).status_code == 403
    dispute = Dispute.objects.get()
    client.post(url, {"action": "resolve", "_selected_action": [dispute.pk], "apply": "1",
                      "decision": "for_pro", "note": "x"})  # fmt: skip
    dispute.refresh_from_db()
    assert dispute.status == "open"


def test_admin_la_page_du_litige_montre_le_texte_et_les_photos_et_audite_chaque_vue(client):
    scene, booking = scheduled()
    booking = advance(booking, Status.ON_SITE)
    photo = services.upload_photo(
        booking=booking, actor=booking.provider.owner, phase="before",
        content=jpeg_with_gps(), idempotency_key="photo-key-" + "1" * 22,
    ).photo  # fmt: skip
    booking = advance(booking, Status.COMPLETED)
    services.report_photo(booking=booking, photo_public_id=photo.public_id, actor=scene.client)
    services.open_dispute(booking=booking, actor=scene.client, reason="damage", description=TEXT)
    client.force_login(ops_user())
    dispute = Dispute.objects.get()
    url = reverse("admin:trust_dispute_change", args=[dispute.pk])
    page = client.get(url)
    text = page.content.decode()
    assert page.status_code == 200 and "Le joint fuit" in text
    assert "signalée par le client" in text  # l'Ops la voit malgré le signalement
    assert f"storage.test/bookings/{booking.public_id}/{photo.public_id}.webp" in text
    assert scene.client.phone not in text and scene.request.landmark not in text
    client.get(url)
    views = AuditEvent.objects.filter(action="bookings.photos.viewed")
    assert views.count() == 2 and views.first().metadata == {"count": 1}
    assert views.first().target_public_id == dispute.public_id


def test_admin_photos_seulement_avec_un_litige_et_reaffichage(client):
    scene, booking = scheduled()
    booking = advance(booking, Status.ON_SITE)
    photo = services.upload_photo(
        booking=booking, actor=booking.provider.owner, phase="before",
        content=jpeg_with_gps(), idempotency_key="photo-key-" + "2" * 22,
    ).photo  # fmt: skip
    services.report_photo(booking=booking, photo_public_id=photo.public_id, actor=scene.client)
    ops = ops_user()
    client.force_login(ops)
    url = reverse("admin:bookings_bookingphoto_changelist")
    # Sans litige : le réaffichage est refusé.
    client.post(url, {"action": "restore", "_selected_action": [photo.pk]}, follow=True)
    photo.refresh_from_db()
    assert photo.hidden_at is not None
    booking = advance(booking, Status.COMPLETED)
    services.open_dispute(booking=booking, actor=scene.client, reason="damage", description=TEXT)
    client.post(url, {"action": "restore", "_selected_action": [photo.pk]}, follow=True)
    photo.refresh_from_db()
    assert photo.hidden_at is None and photo.hidden_by is None
    audit = AuditEvent.objects.get(action="bookings.photo.restored")
    assert audit.actor == ops and audit.metadata == {"phase": "before"}
    assert storage.exists(photo.image_key)


def test_admin_les_photos_ne_s_affichent_pas_dans_la_liste(client):
    scene, booking = scheduled()
    booking = advance(booking, Status.ON_SITE)
    photo = services.upload_photo(
        booking=booking, actor=booking.provider.owner, phase="before",
        content=jpeg_with_gps(), idempotency_key="photo-key-" + "3" * 22,
    ).photo  # fmt: skip
    client.force_login(ops_user())
    page = client.get(reverse("admin:bookings_bookingphoto_changelist"))
    assert page.status_code == 200 and "storage.test" not in page.content.decode()
    assert BookingPhoto.objects.filter(pk=photo.pk).exists() and scene.client


# --- API ---------------------------------------------------------------------------------------


def test_api_ouvrir_un_litige_puis_le_voir_des_deux_cotes(api_client):
    scene, booking = completed()
    client = bearer(api_client, scene.client)
    pro = bearer(api_client, booking.provider.owner, app="pro")
    url = reverse("booking-dispute", args=[booking.public_id])
    detail = client.get(reverse("booking-detail", args=[booking.public_id])).json()
    assert detail["can_dispute"] is True and detail["dispute"] is None
    assert detail["dispute_deadline"]
    response = client.post(url, {"reason": "poor_quality", "description": TEXT}, format="json")
    data = response.json()
    assert (response.status_code, data["status"], data["can_dispute"]) == (200, "disputed", False)
    assert data["dispute"]["status"] == "open" and data["dispute"]["decision"] is None
    assert TEXT not in response.content.decode()  # le texte ne revient jamais par l'API
    assert (
        client.post(url, {"reason": "price", "description": TEXT}, format="json").status_code == 200
    )
    seen = pro.get(reverse("pro-booking-detail", args=[booking.public_id]))
    assert seen.json()["dispute"]["reason"] == "poor_quality" and TEXT not in seen.content.decode()
    services.resolve_dispute(
        dispute=Dispute.objects.get(), decision="no_fault", note="ok", operator=ops_user()
    )
    final = client.get(reverse("booking-detail", args=[booking.public_id])).json()
    assert final["status"] == "closed" and final["dispute"]["decision"] == "no_fault"
    assert "ok" not in final["dispute"]  # la note de l'Ops n'est pas exposée


def test_api_erreurs_du_litige(api_client):
    scene, booking = completed()
    client = bearer(api_client, scene.client)
    url = reverse("booking-dispute", args=[booking.public_id])
    for body, status, code in [
        ({"reason": "x", "description": TEXT}, 422, "reason_invalid"),
        ({"reason": "damage", "description": "court"}, 422, "description_invalid"),
        ({"reason": "damage"}, 400, "invalid"),
    ]:
        response = client.post(url, body, format="json")
        assert (response.status_code, response.json()["code"]) == (status, code)
        assert "court" not in response.content.decode() or code == "invalid"
    Booking.objects.filter(pk=booking.pk).update(
        dispute_deadline=timezone.now() - timedelta(minutes=1)
    )
    response = client.post(url, {"reason": "damage", "description": TEXT}, format="json")
    assert (response.status_code, response.json()["code"]) == (409, "dispute_window_closed")
    detail = client.get(reverse("booking-detail", args=[booking.public_id])).json()
    assert detail["can_dispute"] is False


def test_api_litige_refuse_a_un_autre_compte_au_pro_et_sans_session(api_client):
    _, booking = completed()
    url = reverse("booking-dispute", args=[booking.public_id])
    body = {"reason": "damage", "description": TEXT}
    assert (
        bearer(api_client, CompleteUserFactory()).post(url, body, format="json").status_code == 404
    )
    pro = bearer(api_client, booking.provider.owner, app="pro")
    assert pro.post(url, body, format="json").status_code == 404
    api_client.credentials()
    assert api_client.post(url, body, format="json").status_code == 401
    assert not Dispute.objects.exists()
