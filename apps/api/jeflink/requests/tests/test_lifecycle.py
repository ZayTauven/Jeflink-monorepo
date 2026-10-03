from datetime import timedelta
from itertools import product

import pytest
from django.contrib.auth.models import Group
from django.urls import reverse
from django.utils import timezone

from jeflink.accounts.deletion import _anonymize
from jeflink.accounts.models import User
from jeflink.analytics.models import UnservedDemand
from jeflink.catalog.tests.factories import TradeFactory
from jeflink.common.errors import DomainError
from jeflink.requests import services, tasks
from jeflink.requests.models import ServiceRequest
from jeflink.requests.selectors import effective_status, request_for_client, requests_for_client
from jeflink.trust.models import AuditEvent
from jeflink.zones.tests.factories import ZoneFactory

from .factories import ServiceRequestFactory

pytestmark = pytest.mark.django_db
Status = ServiceRequest.Status


@pytest.mark.parametrize(("start", "to"), list(product(Status.values, Status.values)))
def test_chaque_couple_de_la_table_de_transitions(start, to):
    request = ServiceRequestFactory(status=start)
    if to in services.TRANSITIONS[start]:
        services.transition_request(request, to, reason="test")
        request.refresh_from_db()
        assert request.status == to
        if to in {Status.EXPIRED, Status.CANCELLED}:
            assert request.closed_at is not None and request.close_reason == "test"
    else:
        with pytest.raises(DomainError) as exc:
            services.transition_request(request, to)
        assert exc.value.code == "transition_not_allowed" and exc.value.status_code == 409
        request.refresh_from_db()
        assert request.status == start


@pytest.mark.parametrize("to", [Status.OPEN, Status.QUOTED])
def test_retour_apres_desistement_pose_une_nouvelle_echeance(to):
    old = timezone.now() + timedelta(hours=1)
    request = ServiceRequestFactory(status=Status.BOOKED, expires_at=old)
    services.transition_request(request, to)
    assert request.expires_at > old + timedelta(hours=60)


def test_retour_de_quoted_a_open_garde_l_echeance():
    expires = timezone.now() + timedelta(hours=5)
    request = ServiceRequestFactory(status=Status.QUOTED, expires_at=expires)
    services.transition_request(request, Status.OPEN)
    assert request.expires_at == expires


# --- Annulation -------------------------------------------------------------------------------


@pytest.mark.parametrize("start", [Status.OPEN, Status.QUOTED])
def test_le_client_annule_sa_demande(start):
    request = ServiceRequestFactory(status=start)
    services.cancel_request(request=request, actor=request.client, reason="found_other")
    request.refresh_from_db()
    assert request.status == Status.CANCELLED and request.close_reason == "found_other"
    event = AuditEvent.objects.get(action="requests.request.cancelled")
    assert event.metadata == {"from_status": start, "reason": "found_other", "has_note": False}


def test_annulation_en_needs_zone():
    request = ServiceRequestFactory(status=Status.NEEDS_ZONE, zone=None, expires_at=None)
    services.cancel_request(request=request, actor=request.client, reason="price")
    request.refresh_from_db()
    assert request.status == Status.CANCELLED


@pytest.mark.parametrize("start", [Status.BOOKED, Status.EXPIRED, Status.CANCELLED])
def test_annulation_refusee_une_fois_close_ou_reservee(start):
    request = ServiceRequestFactory(status=start)
    with pytest.raises(DomainError) as exc:
        services.cancel_request(request=request, actor=request.client, reason="price")
    assert (exc.value.code, exc.value.status_code) == ("request_closed", 409)


def test_annulation_par_un_autre_compte_est_un_404(complete_user_factory):
    request = ServiceRequestFactory()
    with pytest.raises(DomainError) as exc:
        services.cancel_request(request=request, actor=complete_user_factory(), reason="price")
    assert exc.value.status_code == 404
    request.refresh_from_db()
    assert request.status == Status.OPEN


@pytest.mark.parametrize(
    ("reason", "note", "code"),
    [
        ("inconnu", "", "reason_invalid"),
        ("too_far", "", "reason_invalid"),  # motif du pro, pas du client
        ("other", "", "note_invalid"),
        ("other", "Appelez le 77 123 45 67", "note_invalid"),
        ("price", "x" * 201, "note_invalid"),
    ],
)
def test_motif_et_note_invalides(reason, note, code):
    request = ServiceRequestFactory()
    with pytest.raises(DomainError) as exc:
        services.cancel_request(request=request, actor=request.client, reason=reason, note=note)
    assert exc.value.code == code and exc.value.status_code == 422


def test_motif_autre_avec_note_sans_la_journaliser():
    request = ServiceRequestFactory()
    services.cancel_request(
        request=request, actor=request.client, reason="other", note="Mon voisin est venu"
    )
    event = AuditEvent.objects.get(action="requests.request.cancelled")
    assert event.metadata["has_note"] is True
    assert "voisin" not in str(event.metadata)


# --- Rattachement à une zone ------------------------------------------------------------------


@pytest.fixture
def needs_zone():
    trade = TradeFactory()
    request = ServiceRequestFactory(
        status=Status.NEEDS_ZONE,
        zone=None,
        expires_at=None,
        zone_text="keur massar",
        trade=trade,
        urgent=True,
    )
    return request, trade


def test_attach_zone_ouvre_la_demande_avec_une_echeance(needs_zone, user_factory):
    request, trade = needs_zone
    zone = ZoneFactory(trades=[trade])
    ops = user_factory(is_staff=True)
    services.attach_zone(request=request, zone=zone, operator=ops)
    request.refresh_from_db()
    assert request.status == Status.OPEN and request.zone == zone and request.zone_text == ""
    # Urgente : 24 h à partir du rattachement, pas de la création.
    assert timedelta(hours=23) < request.expires_at - timezone.now() <= timedelta(hours=24)
    event = AuditEvent.objects.get(action="requests.request.zone_attached")
    assert event.actor_kind == "ops" and event.metadata == {"zone_slug": zone.slug}


def test_attach_zone_refuse_un_metier_non_ouvert_ou_une_zone_inactive(needs_zone, user_factory):
    request, trade = needs_zone
    ops = user_factory(is_staff=True)
    with pytest.raises(DomainError) as exc:
        services.attach_zone(request=request, zone=ZoneFactory(), operator=ops)
    assert exc.value.code == "trade_not_in_zone"
    with pytest.raises(DomainError) as exc:
        services.attach_zone(
            request=request, zone=ZoneFactory(trades=[trade], is_active=False), operator=ops
        )
    assert exc.value.code == "zone_inactive"


def test_attach_zone_refuse_une_demande_deja_ouverte(user_factory):
    request = ServiceRequestFactory()
    with pytest.raises(DomainError) as exc:
        services.attach_zone(request=request, zone=request.zone, operator=user_factory())
    assert exc.value.code == "transition_not_allowed"


@pytest.fixture(autouse=True)
def _second_facteur_valide(monkeypatch):
    monkeypatch.setattr("jeflink.accounts.admin_site.admin_mfa_valid", lambda request: True)


def admin_user(client, group):
    user = User.objects.create_user("+221770000603", is_staff=True)
    user.groups.add(Group.objects.get(name=group))
    client.force_login(user)
    return user


def test_action_d_admin_rattacher(client, needs_zone):
    request, trade = needs_zone
    zone = ZoneFactory(trades=[trade])
    admin_user(client, "Saisie catalogue")
    url = reverse("admin:requests_servicerequest_changelist")
    data = {"action": "attach_to_zone", "_selected_action": [request.pk]}
    page = client.post(url, data)
    assert page.status_code == 200 and "Rattacher" in page.content.decode()
    assert request.landmark not in page.content.decode()
    client.post(url, {**data, "apply": "1", "zone": zone.pk})
    request.refresh_from_db()
    assert request.status == Status.OPEN and request.zone == zone


def test_admin_ne_montre_ni_repere_ni_description(client, needs_zone):
    request, _ = needs_zone
    admin_user(client, "Saisie catalogue")
    request.landmark, request.description = "portail-bleu-secret", "description-secrete"
    request.save()
    list_page = client.get(reverse("admin:requests_servicerequest_changelist")).content.decode()
    detail = client.get(
        reverse("admin:requests_servicerequest_change", args=[request.pk])
    ).content.decode()
    for text in (list_page, detail):
        assert "portail-bleu-secret" not in text and "description-secrete" not in text


def test_validation_pros_ne_peut_pas_rattacher(client, needs_zone):
    request, _ = needs_zone
    admin_user(client, "Validation pros")
    url = reverse("admin:requests_servicerequest_changelist")
    response = client.post(
        url, {"action": "attach_to_zone", "_selected_action": [request.pk], "apply": "1"}
    )
    assert response.status_code == 403
    request.refresh_from_db()
    assert request.status == Status.NEEDS_ZONE


# --- Expiration, purge, anonymisation ---------------------------------------------------------


def test_expiration_des_demandes_echues_et_signal_no_quote():
    past = timezone.now() - timedelta(minutes=1)
    due = ServiceRequestFactory(expires_at=past)
    quoted_before = ServiceRequestFactory(
        expires_at=past, status=Status.QUOTED, first_quoted_at=past - timedelta(hours=1)
    )
    future = ServiceRequestFactory()
    waiting = ServiceRequestFactory(status=Status.NEEDS_ZONE, zone=None, expires_at=None)
    assert services.expire_due() == 2
    for request in (due, quoted_before, future, waiting):
        request.refresh_from_db()
    assert due.status == quoted_before.status == Status.EXPIRED
    assert due.close_reason == "expired" and due.closed_at
    assert future.status == Status.OPEN and waiting.status == Status.NEEDS_ZONE
    signals = UnservedDemand.objects.all()
    assert [s.reason for s in signals] == ["no_quote"]  # seulement sans aucun devis
    assert not {"user", "client"} & {f.name for f in UnservedDemand._meta.get_fields()}


def test_expiration_idempotente_et_via_la_tache():
    ServiceRequestFactory(expires_at=timezone.now() - timedelta(minutes=1))
    assert tasks.expire_due() == {"requests": 1, "quotes": 0}
    assert tasks.expire_due() == {"requests": 0, "quotes": 0}


def test_une_demande_reservee_n_expire_pas():
    request = ServiceRequestFactory(
        status=Status.BOOKED, expires_at=timezone.now() - timedelta(hours=1)
    )
    assert services.expire_due() == 0
    request.refresh_from_db()
    assert request.status == Status.BOOKED


def test_statut_affiche_expire_meme_si_la_tache_a_du_retard():
    late = ServiceRequestFactory(expires_at=timezone.now() - timedelta(minutes=10))
    assert late.status == Status.OPEN and effective_status(late) == Status.EXPIRED
    assert effective_status(ServiceRequestFactory()) == Status.OPEN
    booked = ServiceRequestFactory(status=Status.BOOKED, expires_at=late.expires_at)
    assert effective_status(booked) == Status.BOOKED


def test_purge_vide_repere_et_position_apres_30_jours():
    from django.contrib.gis.geos import Point

    old = timezone.now() - timedelta(days=31)
    recent = timezone.now() - timedelta(days=10)
    point = Point(-17.4, 14.7, srid=4326)
    expired = ServiceRequestFactory(
        status=Status.EXPIRED, closed_at=old, location=point, landmark="repere"
    )
    cancelled = ServiceRequestFactory(status=Status.CANCELLED, closed_at=old, landmark="repere")
    young = ServiceRequestFactory(status=Status.CANCELLED, closed_at=recent, landmark="repere")
    live = ServiceRequestFactory(landmark="repere")
    assert services.purge_locations() == 2
    for request in (expired, cancelled, young, live):
        request.refresh_from_db()
    assert (expired.landmark, expired.location, cancelled.landmark) == ("", None, "")
    assert young.landmark == "repere" and live.landmark == "repere"
    assert tasks.purge_locations() == 0


def test_anonymiseur_annule_les_demandes_ouvertes_et_vide_les_donnees():
    client = ServiceRequestFactory().client
    open_ = ServiceRequestFactory(client=client)
    waiting = ServiceRequestFactory(
        client=client, status=Status.NEEDS_ZONE, zone=None, expires_at=None, zone_text="keur"
    )
    done = ServiceRequestFactory(
        client=client, status=Status.EXPIRED, closed_at=timezone.now(), description="secret"
    )
    other = ServiceRequestFactory()
    _anonymize(client, reason="user_request")
    for request in (open_, waiting, done, other):
        request.refresh_from_db()
    assert open_.status == waiting.status == Status.CANCELLED
    assert open_.close_reason == "account_deleted"
    assert (open_.landmark, open_.description, waiting.zone_text, done.description) == ("",) * 4
    assert done.status == Status.EXPIRED
    assert other.status == Status.OPEN and other.landmark


def test_selecteurs_par_client(complete_user_factory):
    mine = ServiceRequestFactory()
    ServiceRequestFactory()
    assert list(requests_for_client(user=mine.client)) == [mine]
    assert request_for_client(user=mine.client, public_id=mine.public_id) == mine
    with pytest.raises(DomainError) as exc:
        request_for_client(user=complete_user_factory(), public_id=mine.public_id)
    assert exc.value.status_code == 404
