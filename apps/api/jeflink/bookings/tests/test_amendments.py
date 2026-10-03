"""Avenants (spec 004, tâche 6) : proposition, retrait, acceptation (seule écriture du montant),
refus, caducité, plafond, concurrence, API."""

from concurrent.futures import ThreadPoolExecutor

import pytest
from django.db import connection
from django.urls import reverse

from jeflink.accounts.tests.factories import CompleteUserFactory
from jeflink.bookings import services
from jeflink.bookings.machine import Status
from jeflink.bookings.models import Amendment, Booking, BookingEvent
from jeflink.common.errors import DomainError
from jeflink.notifications import events
from jeflink.providers.models import Provider
from jeflink.providers.tests.factories import VerifiedProviderFactory
from jeflink.requests.quotes import QuoteLineInput
from jeflink.requests.tests.test_requests_api import bearer
from jeflink.trust.models import AuditEvent

from .factories import advance, scheduled
from .test_services import expect

pytestmark = pytest.mark.django_db


def key(n: int = 0) -> str:
    return f"amend-key-{n:023d}"


def in_progress():
    scene, booking = scheduled()
    return scene, advance(booking, Status.IN_PROGRESS)  # montant du devis : 15 000


def propose(booking, *, total=22_000, n=0, reason="extra_work", note="", lines=None):
    lines = lines or (QuoteLineInput("labor", total - 5_000, "Main-d'œuvre"),
                      QuoteLineInput("parts", 5_000, "Joint"))  # fmt: skip
    return services.propose_amendment(
        booking=booking, actor=booking.provider.owner, reason=reason, note=note,
        lines=lines, total_xof=total, idempotency_key=key(n),
    )  # fmt: skip


@pytest.fixture
def notified(monkeypatch):
    sent = []
    monkeypatch.setattr(
        events, "notify", lambda kind, recipients, ref: sent.append((kind, list(recipients), ref))
    )
    return sent


# --- Proposition -------------------------------------------------------------------------------


def test_le_pro_propose_le_nouveau_prix_complet(notified):
    scene, booking = in_progress()
    result = propose(booking, note="Joint et raccord remplacés")
    amendment = result.amendment
    assert result.created and amendment.status == "proposed"
    assert (amendment.previous_amount_xof, amendment.total_xof) == (15_000, 22_000)
    assert [(ln.kind, ln.amount_xof) for ln in amendment.lines.all()] == [
        ("labor", 17_000),
        ("parts", 5_000),
    ]
    booking.refresh_from_db()
    assert booking.amount_xof == 15_000 and booking.original_amount_xof == 15_000  # inchangé
    assert (events.AMENDMENT_PROPOSED, [scene.client], booking.public_id) in notified
    audit = AuditEvent.objects.get(action="bookings.amendment.proposed")
    assert audit.metadata == {"previous_xof": 15_000, "total_xof": 22_000, "reason": "extra_work"}
    assert "joint" not in str(audit.metadata).lower()  # la note n'est jamais auditée


def test_proposition_rejouee_rend_le_meme_avenant():
    _, booking = in_progress()
    first = propose(booking)
    again = propose(booking)
    assert (first.created, again.created) == (True, False)
    assert again.amendment.pk == first.amendment.pk and Amendment.objects.count() == 1
    with expect("idempotency_key_reused"):
        propose(booking, total=23_000)


@pytest.mark.parametrize("bad_key", ["", "court"])
def test_cle_d_idempotence_obligatoire(bad_key):
    _, booking = in_progress()
    with expect("idempotency_key_required", 400):
        services.propose_amendment(
            booking=booking, actor=booking.provider.owner, reason="parts", note="",
            lines=(QuoteLineInput("parts", 20_000),), total_xof=20_000, idempotency_key=bad_key,
        )  # fmt: skip


def test_une_baisse_est_permise_et_le_total_doit_changer():
    _, booking = in_progress()
    assert propose(booking, total=9_000, reason="visit_diagnosis").created
    with expect("amendment_pending"):
        propose(booking, total=8_000, n=1)
    _, other = in_progress()
    with expect("amendment_total_invalid", 422):
        propose(other, total=15_000)  # même prix : rien à valider


@pytest.mark.parametrize(
    "bad",
    [
        {"total": 0, "lines": ()},
        {"total": 22_000, "lines": (QuoteLineInput("labor", 21_000),)},  # somme fausse
        {"total": 22_000, "lines": (QuoteLineInput("autre", 22_000),)},  # genre inconnu
        {"total": 22_000, "lines": (QuoteLineInput("labor", 22_000, "x" * 61),)},
        {"total": 22_000, "lines": (QuoteLineInput("labor", 0), QuoteLineInput("parts", 22_000))},
        {"total": 5_000_001, "lines": (QuoteLineInput("labor", 5_000_001),)},  # plafond
        {"total": 22_000, "lines": tuple(QuoteLineInput("labor", 1_000) for _ in range(9))},
    ],
    ids=["zero", "somme", "genre", "libelle", "ligne_nulle", "plafond", "trop_de_lignes"],
)
def test_total_invalide(bad):
    _, booking = in_progress()
    code = "text_too_long" if bad["total"] == 22_000 and bad["lines"][0].label else None
    with pytest.raises(DomainError) as exc:
        propose(booking, total=bad["total"], lines=bad["lines"])
    assert exc.value.code == (code or "amendment_total_invalid") and exc.value.status_code == 422
    assert not Amendment.objects.exists()


def test_le_plafond_est_celui_d_un_devis(settings):
    settings.QUOTE_MAX_XOF = 30_000
    _, booking = in_progress()
    assert propose(booking, total=30_000, lines=(QuoteLineInput("labor", 30_000),)).created


def test_motif_et_note():
    _, booking = in_progress()
    with expect("amendment_reason_invalid", 422):
        propose(booking, reason="gourmandise")
    with expect("note_invalid", 422):
        propose(booking, reason="other", note="")  # « autre » exige une note
    with expect("note_invalid", 422):
        propose(booking, note="Appelez-moi au 77 123 45 67")
    assert propose(booking, reason="other", note="Pièce spéciale commandée").created


def test_proposition_refusee_hors_in_progress_a_un_autre_pro_ou_suspendu():
    scene, booking = scheduled()
    with expect("transition_not_allowed"):
        propose(booking)
    _, running = in_progress()
    with expect("not_found", 404):
        services.propose_amendment(
            booking=running, actor=VerifiedProviderFactory().owner, reason="parts", note="",
            lines=(QuoteLineInput("parts", 20_000),), total_xof=20_000, idempotency_key=key(),
        )  # fmt: skip
    Provider.objects.filter(pk=running.provider_id).update(status="suspended")
    with expect("provider_not_verified", 403):
        propose(running)
    assert scene.client


def test_trois_propositions_au_plus_par_reservation():
    scene, booking = in_progress()
    for n, total in enumerate((20_000, 25_000, 30_000)):
        created = propose(booking, total=total, n=n).amendment
        services.decline_amendment(amendment=created, actor=scene.client)
    with expect("amendment_limit"):
        propose(booking, total=40_000, n=3)


def test_le_plafond_de_propositions_est_un_reglage(settings):
    settings.BOOKING_AMENDMENTS_MAX = 1
    scene, booking = in_progress()
    services.decline_amendment(amendment=propose(booking).amendment, actor=scene.client)
    with expect("amendment_limit"):
        propose(booking, total=30_000, n=1)


# --- Retrait -----------------------------------------------------------------------------------


def test_le_pro_retire_son_avenant():
    _, booking = in_progress()
    amendment = propose(booking).amendment
    owner = booking.provider.owner
    result = services.withdraw_amendment(amendment=amendment, actor=owner)
    assert result.status == "withdrawn" and result.decided_at
    assert services.withdraw_amendment(amendment=amendment, actor=owner).status == "withdrawn"
    assert AuditEvent.objects.filter(action="bookings.amendment.withdrawn").count() == 1
    assert propose(booking, total=24_000, n=1).created  # une place se libère


def test_retrait_refuse_apres_la_decision_ou_a_un_autre_pro():
    scene, booking = in_progress()
    amendment = propose(booking).amendment
    with expect("not_found", 404):
        services.withdraw_amendment(amendment=amendment, actor=VerifiedProviderFactory().owner)
    services.accept_amendment(amendment=amendment, actor=scene.client)
    with expect("amendment_not_pending"):
        services.withdraw_amendment(amendment=amendment, actor=booking.provider.owner)


# --- Décision du client ------------------------------------------------------------------------


def test_le_client_accepte_le_montant_change_par_une_transition(notified):
    scene, booking = in_progress()
    amendment = propose(booking).amendment
    notified.clear()
    result = services.accept_amendment(amendment=amendment, actor=scene.client)
    assert (result.amount_xof, result.original_amount_xof, result.status) == (
        22_000,
        15_000,
        Status.IN_PROGRESS,
    )
    amendment.refresh_from_db()
    assert amendment.status == "accepted" and amendment.decided_at
    event = BookingEvent.objects.filter(booking=booking).latest("id")
    assert (event.from_status, event.to_status, event.actor_kind, event.reason) == (
        Status.IN_PROGRESS,
        Status.IN_PROGRESS,
        "client",
        "amendment_accepted",
    )
    assert event.metadata["amendment"] == {
        "public_id": str(amendment.public_id),
        "previous_xof": 15_000,
        "total_xof": 22_000,
    }
    audit = AuditEvent.objects.get(action="bookings.amendment.accepted")
    assert audit.actor == scene.client
    assert audit.metadata == {"previous_xof": 15_000, "total_xof": 22_000}
    assert (events.AMENDMENT_DECIDED, [booking.provider.owner], booking.public_id) in notified
    # Rejeu : 200, ni événement ni audit de plus.
    before = BookingEvent.objects.filter(booking=booking).count()
    services.accept_amendment(amendment=amendment, actor=scene.client)
    assert BookingEvent.objects.filter(booking=booking).count() == before


def test_un_second_avenant_part_du_montant_accepte():
    scene, booking = in_progress()
    services.accept_amendment(amendment=propose(booking).amendment, actor=scene.client)
    second = propose(booking, total=30_000, n=1).amendment
    assert second.previous_amount_xof == 22_000
    services.accept_amendment(amendment=second, actor=scene.client)
    booking.refresh_from_db()
    assert (booking.amount_xof, booking.original_amount_xof) == (30_000, 15_000)


def test_le_client_refuse_le_prix_ne_bouge_pas(notified):
    scene, booking = in_progress()
    amendment = propose(booking).amendment
    result = services.decline_amendment(amendment=amendment, actor=scene.client)
    amendment.refresh_from_db()
    assert amendment.status == "declined" and result.amount_xof == 15_000
    assert not BookingEvent.objects.filter(booking=booking, reason="amendment_accepted").exists()
    assert AuditEvent.objects.filter(action="bookings.amendment.declined").count() == 1
    assert any(kind == events.AMENDMENT_DECIDED for kind, *_ in notified)
    services.decline_amendment(amendment=amendment, actor=scene.client)  # rejeu
    with expect("amendment_not_pending"):
        services.accept_amendment(amendment=amendment, actor=scene.client)


def test_decision_refusee_a_un_autre_compte_et_au_pro():
    scene, booking = in_progress()
    amendment = propose(booking).amendment
    with expect("not_found", 404):
        services.accept_amendment(amendment=amendment, actor=CompleteUserFactory())
    with expect("not_found", 404):  # le pro n'est pas le client de la réservation
        services.accept_amendment(amendment=amendment, actor=booking.provider.owner)
    booking.refresh_from_db()
    assert booking.amount_xof == 15_000 and scene.client


def test_l_avenant_en_attente_devient_caduc_a_la_fin_de_mission():
    scene, booking = in_progress()
    amendment = propose(booking).amendment
    services.complete_work(
        booking=booking, actor=booking.provider.owner, no_code_reason="client_absent",
        photos_pending=True,
    )  # fmt: skip
    amendment.refresh_from_db()
    assert amendment.status == "lapsed" and amendment.decided_at
    booking.refresh_from_db()
    assert booking.amount_xof == 15_000
    with expect("amendment_not_pending"):
        services.accept_amendment(amendment=amendment, actor=scene.client)


def test_ecart_en_pourcentage_et_confirmation_au_dela_du_seuil(settings):
    _, booking = in_progress()
    amendment = propose(booking, total=22_500, lines=(QuoteLineInput("labor", 22_500),)).amendment
    assert services.change_pct(amendment) == 50
    assert services.requires_confirmation(amendment) is False  # 50 % pile : pas au-delà
    amendment.total_xof = 22_501
    assert services.requires_confirmation(amendment) is True
    amendment.total_xof = 7_000  # une baisse n'en demande aucune
    assert services.change_pct(amendment) == -53
    assert services.requires_confirmation(amendment) is False
    settings.AMENDMENT_CONFIRM_THRESHOLD_PCT = 10
    amendment.total_xof = 17_000
    assert services.requires_confirmation(amendment) is True


def test_l_anonymiseur_efface_les_notes_et_libelles_du_pro():
    _, booking = in_progress()
    amendment = propose(booking, note="Pièce spéciale").amendment
    services.anonymize_bookings(booking.provider.owner)
    amendment.refresh_from_db()
    assert amendment.note == "" and {ln.label for ln in amendment.lines.all()} == {""}


# --- Plafond et concurrence --------------------------------------------------------------------


@pytest.mark.django_db(transaction=True, databases="__all__", serialized_rollback=True)
def test_deux_propositions_simultanees_une_seule_en_attente():
    _, booking = in_progress()

    def attempt(n):
        try:
            return propose(booking, total=20_000 + n * 1_000, n=n).created
        except DomainError as exc:
            return exc.code
        finally:
            connection.close()

    with ThreadPoolExecutor(2) as pool:
        results = sorted(map(str, pool.map(attempt, [0, 1])))
    assert results == ["True", "amendment_pending"]
    assert Amendment.objects.filter(status="proposed").count() == 1


@pytest.mark.django_db(transaction=True, databases="__all__", serialized_rollback=True)
def test_accepter_et_retirer_en_meme_temps_un_seul_gagne():
    scene, booking = in_progress()
    amendment = propose(booking).amendment

    def accept(_):
        try:
            services.accept_amendment(amendment=amendment, actor=scene.client)
            return "accepted"
        except DomainError as exc:
            return exc.code
        finally:
            connection.close()

    def withdraw(_):
        try:
            services.withdraw_amendment(amendment=amendment, actor=booking.provider.owner)
            return "withdrawn"
        except DomainError as exc:
            return exc.code
        finally:
            connection.close()

    with ThreadPoolExecutor(2) as pool:
        first = pool.submit(accept, 0)
        second = pool.submit(withdraw, 0)
        results = sorted([first.result(), second.result()])
    assert results in (
        ["accepted", "amendment_not_pending"],
        ["amendment_not_pending", "withdrawn"],
    )
    amendment.refresh_from_db()
    booking.refresh_from_db()
    assert (booking.amount_xof == 22_000) == (amendment.status == "accepted")


@pytest.mark.django_db(transaction=True, databases="__all__", serialized_rollback=True)
def test_deux_acceptations_simultanees_ne_changent_le_montant_qu_une_fois():
    scene, booking = in_progress()
    amendment = propose(booking).amendment

    def accept(_):
        try:
            services.accept_amendment(amendment=amendment, actor=scene.client)
            return "ok"
        except DomainError as exc:
            return exc.code
        finally:
            connection.close()

    with ThreadPoolExecutor(2) as pool:
        assert list(pool.map(accept, [0, 1])) == ["ok", "ok"]  # le rejeu répond 200
    booking.refresh_from_db()
    assert booking.amount_xof == 22_000
    assert BookingEvent.objects.filter(booking=booking, reason="amendment_accepted").count() == 1


# --- API ---------------------------------------------------------------------------------------


def body(**overrides):
    base = {
        "reason": "extra_work",
        "note": "Joint remplacé",
        "total_xof": 22_000,
        "lines": [
            {"kind": "labor", "amount_xof": 17_000, "label": "Main-d'œuvre"},
            {"kind": "parts", "amount_xof": 5_000, "label": "Joint"},
        ],
    }
    return {**base, **overrides}


def post(api, url, data, n=0):
    return api.post(url, data, format="json", HTTP_IDEMPOTENCY_KEY=key(n))


def test_api_le_parcours_complet(api_client):
    scene, booking = in_progress()
    pro = bearer(api_client, booking.provider.owner, app="pro")
    client = bearer(api_client, scene.client)
    create = reverse("pro-booking-amendments", args=[booking.public_id])
    response = post(pro, create, body())
    data = response.json()
    assert response.status_code == 201 and data["status"] == "proposed"
    assert (data["previous_amount_xof"], data["total_xof"], data["change_pct"]) == (
        15_000,
        22_000,
        47,
    )
    assert data["requires_confirmation"] is False and len(data["lines"]) == 2
    assert post(pro, create, body()).status_code == 200  # rejeu
    # Le client voit l'avenant, l'ancien et le nouveau prix ; le montant n'a pas bougé.
    detail = client.get(reverse("booking-detail", args=[booking.public_id])).json()
    assert detail["amount_xof"] == 15_000 and detail["original_amount_xof"] == 15_000
    assert [a["public_id"] for a in detail["amendments"]] == [data["public_id"]]
    pro_detail = pro.get(reverse("pro-booking-detail", args=[booking.public_id])).json()
    assert pro_detail["amendments"][0]["total_xof"] == 22_000
    accept = reverse("booking-amendment-accept", args=[booking.public_id, data["public_id"]])
    response = client.post(accept)
    assert response.status_code == 200
    assert (response.json()["amount_xof"], response.json()["amendments"][0]["status"]) == (
        22_000,
        "accepted",
    )
    assert client.post(accept).status_code == 200  # rejeu
    decline = reverse("booking-amendment-decline", args=[booking.public_id, data["public_id"]])
    response = client.post(decline)
    assert (response.status_code, response.json()["code"]) == (409, "amendment_not_pending")


def test_api_refus_et_retrait(api_client):
    scene, booking = in_progress()
    pro = bearer(api_client, booking.provider.owner, app="pro")
    client = bearer(api_client, scene.client)
    created = post(pro, reverse("pro-booking-amendments", args=[booking.public_id]), body()).json()
    withdraw = reverse("pro-amendment-withdraw", args=[created["public_id"]])
    response = pro.post(withdraw)
    assert (response.status_code, response.json()["amendments"][0]["status"]) == (200, "withdrawn")
    assert pro.post(withdraw).status_code == 200  # rejeu
    again = post(
        pro, reverse("pro-booking-amendments", args=[booking.public_id]), body(total_xof=18_000,
        lines=[{"kind": "labor", "amount_xof": 18_000}]), n=1,
    ).json()  # fmt: skip
    decline = reverse("booking-amendment-decline", args=[booking.public_id, again["public_id"]])
    response = client.post(decline)
    assert response.status_code == 200 and response.json()["amount_xof"] == 15_000
    assert response.json()["amendments"][1]["status"] == "declined"


def test_api_erreurs_de_proposition(api_client):
    scene, booking = in_progress()
    pro = bearer(api_client, booking.provider.owner, app="pro")
    url = reverse("pro-booking-amendments", args=[booking.public_id])
    cases = [
        (body(total_xof=21_000), 422, "amendment_total_invalid"),
        (body(total_xof=15_000, lines=[{"kind": "labor", "amount_xof": 15_000}]), 422,
         "amendment_total_invalid"),
        (body(reason="gourmandise"), 422, "amendment_reason_invalid"),
        (body(note="Appelez le 77 123 45 67"), 422, "note_invalid"),
        (body(lines="x"), 400, "invalid"),
        ({}, 400, "invalid"),
    ]  # fmt: skip
    for data, status, code in cases:
        response = post(pro, url, data)
        assert (response.status_code, response.json()["code"]) == (status, code), data
        assert "77 123" not in response.content.decode()
    assert pro.post(url, body(), format="json").json()["code"] == "idempotency_key_required"
    assert post(pro, url, body()).status_code == 201
    response = post(
        pro, url, body(total_xof=30_000, lines=[{"kind": "labor", "amount_xof": 30_000}]), 1
    )
    assert (response.status_code, response.json()["code"]) == (409, "amendment_pending")
    assert scene.client


def test_api_permissions_des_avenants(api_client):
    scene, booking = in_progress()
    pro = bearer(api_client, booking.provider.owner, app="pro")
    created = post(pro, reverse("pro-booking-amendments", args=[booking.public_id]), body()).json()
    create = reverse("pro-booking-amendments", args=[booking.public_id])
    accept = reverse("booking-amendment-accept", args=[booking.public_id, created["public_id"]])
    withdraw = reverse("pro-amendment-withdraw", args=[created["public_id"]])
    # Le client ne propose ni ne retire ; le pro n'accepte jamais.
    assert post(bearer(api_client, scene.client), create, body(), 1).status_code == 403
    assert bearer(api_client, scene.client).post(withdraw).status_code == 403
    assert pro.post(accept).status_code == 404
    # Un autre compte, un autre pro, personne.
    assert bearer(api_client, CompleteUserFactory()).post(accept).status_code == 404
    stranger = bearer(api_client, VerifiedProviderFactory().owner, app="pro")
    assert stranger.post(withdraw).status_code == 404
    assert post(stranger, create, body(), 2).status_code == 404
    api_client.credentials()
    assert api_client.post(accept).status_code == 401
    assert post(api_client, create, body(), 3).status_code == 401
    booking.refresh_from_db()
    assert booking.amount_xof == 15_000


def test_api_pro_suspendu_ne_propose_ni_ne_retire(api_client):
    _, booking = in_progress()
    pro = bearer(api_client, booking.provider.owner, app="pro")
    created = post(pro, reverse("pro-booking-amendments", args=[booking.public_id]), body()).json()
    Booking.objects.filter(pk=booking.pk)  # la fiche, pas la réservation
    Provider.objects.filter(pk=booking.provider_id).update(status="suspended")
    response = post(pro, reverse("pro-booking-amendments", args=[booking.public_id]), body(), 1)
    assert (response.status_code, response.json()["code"]) == (403, "provider_not_verified")
    response = pro.post(reverse("pro-amendment-withdraw", args=[created["public_id"]]))
    assert (response.status_code, response.json()["code"]) == (403, "provider_not_verified")
