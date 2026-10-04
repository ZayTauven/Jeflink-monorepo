"""Notifications (spec 003) : cinq types, après commit, jamais de donnée personnelle."""

import logging
import uuid

import pytest

from jeflink.bookings import services as booking_services
from jeflink.bookings.machine import Actor
from jeflink.bookings.tests.factories import accept, confirm, make_scene, quote_input
from jeflink.notifications import events
from jeflink.providers.tests.factories import VerifiedProviderFactory
from jeflink.requests import quotes
from jeflink.requests.drafts import RequestDraft
from jeflink.requests.services import attach_zone, create_request
from jeflink.zones.tests.factories import ZoneFactory

pytestmark = pytest.mark.django_db
LOGGER = "jeflink.notifications.events"


def lines(caplog) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.name == LOGGER]


@pytest.fixture
def log(caplog):
    caplog.set_level(logging.INFO, logger=LOGGER)
    return caplog


def test_notify_apres_le_commit_seulement(django_capture_on_commit_callbacks, log, user_factory):
    user, ref = user_factory(), uuid.uuid4()
    with django_capture_on_commit_callbacks(execute=False) as callbacks:
        events.notify(events.QUOTE_RECEIVED, [user], ref)
        assert lines(log) == []  # rien avant le commit
    assert len(callbacks) == 1
    callbacks[0]()
    assert lines(log) == [f"notify kind=quote.received recipients={user.public_id} ref={ref}"]


def test_type_inconnu_refuse(user_factory):
    with pytest.raises(ValueError):
        events.notify("request.deleted", [user_factory()], uuid.uuid4())


def test_sans_destinataire_rien_n_est_planifie(django_capture_on_commit_callbacks, log):
    with django_capture_on_commit_callbacks(execute=True) as callbacks:
        events.notify(events.REQUEST_NEW, [], uuid.uuid4())
    assert callbacks == [] and lines(log) == []


def test_destinataires_dedoublonnes(django_capture_on_commit_callbacks, log, user_factory):
    user = user_factory()
    with django_capture_on_commit_callbacks(execute=True):
        events.notify(events.REQUEST_NEW, [user, user.public_id], uuid.uuid4())
    assert lines(log)[0].count(str(user.public_id)) == 1


def test_un_adaptateur_en_panne_ne_casse_pas_l_action(
    django_capture_on_commit_callbacks, log, user_factory, monkeypatch
):
    class Broken:
        name = "broken"

        def deliver(self, **kwargs):
            raise RuntimeError("0771234567 Rue 12")

    monkeypatch.setattr(events, "get_adapter", lambda: Broken())
    with django_capture_on_commit_callbacks(execute=True):
        events.notify(events.QUOTE_RECEIVED, [user_factory()], uuid.uuid4())
    assert lines(log)[0].startswith("notify_failed kind=quote.received")
    assert "0771234567" not in "".join(r.getMessage() for r in log.records)


def test_choix_de_l_adaptateur(settings):
    assert isinstance(events.get_adapter(), events.LogAdapter)  # test : journal
    settings.NOTIFICATIONS_ADAPTER = "none"
    assert isinstance(events.get_adapter(), events.NullAdapter)
    settings.NOTIFICATIONS_ADAPTER = "sms"
    with pytest.raises(ValueError):
        events.get_adapter()
    settings.NOTIFICATIONS_ADAPTER = ""
    settings.DJANGO_ENV = "production"
    assert isinstance(events.get_adapter(), events.NullAdapter)


# --- Les cinq types, branchés sur les services --------------------------------------------------


def kinds(log) -> list[str]:
    return [line.split()[1].removeprefix("kind=") for line in lines(log)]


def test_request_new_vers_les_pros_eligibles(django_capture_on_commit_callbacks, log):
    scene = make_scene(pros=0)
    pro = VerifiedProviderFactory(trades=[scene.trade], zones=[scene.zone])
    outsider = VerifiedProviderFactory(trades=[scene.trade], zones=[ZoneFactory()])
    with django_capture_on_commit_callbacks(execute=True):
        result = create_request(
            client=scene.client,
            draft=RequestDraft(
                trade_slug=scene.trade.slug,
                zone_slug=scene.zone.slug,
                landmark="portail bleu",
                description="Fuite sous l'évier",
            ),
            channel="web",
            idempotency_key="n" * 30,
        )
    (line,) = lines(log)
    assert line == (
        f"notify kind=request.new recipients={pro.owner.public_id} ref={result.request.public_id}"
    )
    assert str(outsider.owner.public_id) not in line


def test_request_new_apres_le_rattachement_a_une_zone(
    django_capture_on_commit_callbacks, log, user_factory
):
    scene = make_scene(pros=0)
    pro = VerifiedProviderFactory(trades=[scene.trade], zones=[scene.zone])
    with django_capture_on_commit_callbacks(execute=True):
        request = create_request(
            client=scene.client,
            draft=RequestDraft(
                trade_slug=scene.trade.slug,
                zone_text="quartier inconnu",
                landmark="portail",
                description="Fuite sous l'évier",
            ),
            channel="web",
            idempotency_key="u" * 30,
        ).request
    assert lines(log) == []  # needs_zone : personne n'est prévenu
    with django_capture_on_commit_callbacks(execute=True):
        attach_zone(request=request, zone=scene.zone, operator=user_factory(is_staff=True))
    assert kinds(log) == ["request.new"] and str(pro.owner.public_id) in lines(log)[0]


def test_les_cinq_types_sur_le_parcours_complet(django_capture_on_commit_callbacks, log):
    with django_capture_on_commit_callbacks(execute=True):
        scene = make_scene(pros=1)  # quote.received (le client est prévenu du devis)
    assert kinds(log) == ["quote.received"]
    with django_capture_on_commit_callbacks(execute=True):
        booking = accept(scene)  # booking.to_confirm vers le pro
    assert kinds(log)[-1] == "booking.to_confirm"
    assert lines(log)[-1].split("recipients=")[1].split()[0] == str(
        scene.providers[0].owner.public_id
    )
    with django_capture_on_commit_callbacks(execute=True):
        confirm(booking)  # booking.scheduled vers le client
    assert kinds(log)[-1] == "booking.scheduled"
    assert str(scene.client.public_id) in lines(log)[-1]
    with django_capture_on_commit_callbacks(execute=True):
        booking_services.cancel_booking(
            booking=booking, actor=scene.client, actor_kind=Actor.CLIENT, reason="price"
        )
    assert kinds(log)[-1] == "booking.cancelled"
    assert str(scene.providers[0].owner.public_id) in lines(log)[-1]  # le pro est prévenu
    assert set(kinds(log)) == {"quote.received", "booking.to_confirm", "booking.scheduled",
                               "booking.cancelled"}  # fmt: skip


def test_annulation_par_le_pro_ou_le_systeme_previent_le_client(
    django_capture_on_commit_callbacks, log
):
    scene = make_scene(pros=2)
    booking = accept(scene, 0)
    with django_capture_on_commit_callbacks(execute=True):
        booking_services.cancel_booking(
            booking=booking, actor=scene.providers[0].owner, actor_kind=Actor.PRO,
            reason="unavailable",
        )  # fmt: skip
    line = [entry for entry in lines(log) if "booking.cancelled" in entry][-1]
    assert str(scene.client.public_id) in line
    assert str(scene.providers[0].owner.public_id) not in line  # celui qui annule n'est pas prévenu


def test_un_devis_previent_le_client(django_capture_on_commit_callbacks, log):
    scene = make_scene(pros=0)
    pro = VerifiedProviderFactory(trades=[scene.trade], zones=[scene.zone])
    with django_capture_on_commit_callbacks(execute=True):
        quotes.submit_quote(
            provider=pro, request=scene.request, content=quote_input(), idempotency_key="q" * 30
        )
    assert lines(log) == [
        f"notify kind=quote.received recipients={scene.client.public_id} "
        f"ref={scene.request.public_id}"
    ]


def test_aucune_donnee_personnelle_dans_les_lignes_ecrites(django_capture_on_commit_callbacks, log):
    scene = make_scene(pros=1)
    scene.client.display_name = "Awa Ndiaye"
    scene.client.save()
    scene.request.landmark = "derrière la mosquée Almadies"
    scene.request.description = "Rappelez le 77 123 45 67"
    scene.request.save()
    with django_capture_on_commit_callbacks(execute=True):
        booking = accept(scene)
        confirm(booking)
        booking_services.cancel_booking(
            booking=booking, actor=scene.client, actor_kind=Actor.CLIENT, reason="other",
            note="Un vrai motif libre",
        )  # fmt: skip
    text = "\n".join(lines(log))
    assert text
    for secret in (
        scene.client.phone, scene.providers[0].owner.phone, "Awa", "Ndiaye", "mosquée",
        "123 45 67", "motif libre", scene.providers[0].business_name, scene.trade.name_fr,
    ):  # fmt: skip
        assert secret not in text
    allowed = {"notify", "kind", "recipients", "ref"}
    for line in lines(log):
        keys = {part.split("=")[0] for part in line.split()}
        assert keys <= allowed
        assert uuid.UUID(line.split("ref=")[1])  # la référence est un public_id
