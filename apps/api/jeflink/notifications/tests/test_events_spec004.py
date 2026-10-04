"""Notifications de la spec 004 : les 11 nouveaux types sont branchés, et ne transportent que le
type et des public_id (jamais un nom, un numéro, un code, un prix, un texte libre)."""

import logging
import re
from datetime import timedelta

import pytest
from django.contrib.auth.models import Group
from django.utils import timezone

from jeflink.accounts.models import User
from jeflink.bookings import services
from jeflink.bookings.machine import Status
from jeflink.bookings.models import Booking
from jeflink.bookings.tests.factories import advance, scheduled
from jeflink.notifications import events
from jeflink.requests.quotes import QuoteLineInput
from jeflink.trust.models import Dispute

pytestmark = pytest.mark.django_db
LOGGER = "jeflink.notifications.events"
UUID = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
LINE = re.compile(rf"^notify kind=([a-z_.]+) recipients=({UUID}(,{UUID})*) ref=({UUID})$")
NEW_KINDS = {
    events.COMPLETION_CODE_SMS,
    events.AMENDMENT_PROPOSED,
    events.DISPUTE_REMINDER,
    events.BOOKING_PROGRESS,
    events.AMENDMENT_DECIDED,
    events.BOOKING_COMPLETED,
    events.NO_SHOW_CHECK,
    events.NO_SHOW_CONTESTED,
    events.BOOKING_DISPUTED,
    events.DISPUTE_DECIDED,
    events.BOOKING_CLOSED,
}


@pytest.fixture
def lines(caplog, django_capture_on_commit_callbacks):
    caplog.set_level(logging.INFO, logger=LOGGER)
    collected: list[str] = []

    class Run:
        def __call__(self, func):
            with django_capture_on_commit_callbacks(execute=True):
                result = func()
            collected[:] = [r.getMessage() for r in caplog.records if r.name == LOGGER]
            return result

        @property
        def all(self):
            return collected

    return Run()


def test_les_onze_types_sont_declares_et_trois_partent_par_sms():
    assert NEW_KINDS <= events.KINDS and len(NEW_KINDS) == 11
    assert {
        events.COMPLETION_CODE_SMS,
        events.AMENDMENT_PROPOSED,
        events.DISPUTE_REMINDER,
    } == events.SMS_KINDS


def test_chaque_type_est_declenche_par_son_parcours_sans_donnee_personnelle(lines):
    secrets_to_find = []

    # Parcours nominal : départ, arrivée, début, avenant, fin, rappel, clôture.
    scene, booking = scheduled()
    secrets_to_find += [scene.client.phone, booking.provider.owner.phone, scene.request.landmark]
    owner = booking.provider.owner
    lines(lambda: services.mark_en_route(booking=booking, actor=owner))
    lines(lambda: services.mark_arrived(booking=booking, actor=owner))
    lines(lambda: services.start_work(booking=booking, actor=owner, photos_pending=True))
    amendment = lines(
        lambda: services.propose_amendment(
            booking=booking, actor=owner, reason="parts", note="Pièce spéciale",
            lines=(QuoteLineInput("parts", 22_222),), total_xof=22_222,
            idempotency_key="notif-key-" + "0" * 22,
        ).amendment
    )  # fmt: skip
    lines(lambda: services.accept_amendment(amendment=amendment, actor=scene.client))
    code = services.visible_completion_code(Booking.objects.get(pk=booking.pk))
    lines(
        lambda: services.complete_work(booking=booking, actor=owner, code=code, photos_pending=True)
    )
    Booking.objects.filter(pk=booking.pk).update(
        dispute_deadline=timezone.now() + timedelta(hours=3)
    )
    lines(services.remind_disputes)
    Booking.objects.filter(pk=booking.pk).update(
        dispute_deadline=timezone.now() - timedelta(minutes=1)
    )
    lines(services.close_due)
    nominal = list(lines.all)

    # No-show : interrogation du client puis contestation du pro.
    scene2, other = scheduled()
    end = timezone.now() - timedelta(hours=3)
    Booking.objects.filter(pk=other.pk).update(slot_start=end - timedelta(hours=4), slot_end=end)
    other.refresh_from_db()
    lines(services.no_show_check)
    lines(lambda: services.declare_no_show(booking=other, actor=scene2.client))
    lines(
        lambda: services.contest_no_show(
            booking=other, actor=other.provider.owner, note="J'étais présent"
        )
    )
    no_show = list(lines.all)

    # Litige : ouverture puis décision.
    scene3, third = scheduled()
    third = advance(third, Status.COMPLETED)
    lines(
        lambda: services.open_dispute(
            booking=third, actor=scene3.client, reason="damage",
            description="Le robinet fuit toujours depuis le passage.",
        )
    )  # fmt: skip
    ops = User.objects.create_user("+221770000931", is_staff=True)
    ops.groups.add(Group.objects.get(name="Médiation"))
    lines(
        lambda: services.resolve_dispute(
            dispute=Dispute.objects.get(), decision="no_fault", note="Rien à signaler", operator=ops
        )
    )
    dispute = list(lines.all)

    every = nominal + no_show + dispute
    kinds = set()
    for line in every:
        match = LINE.match(line)
        assert match, f"ligne hors format : {line}"
        kinds.add(match.group(1))
    assert kinds >= NEW_KINDS, NEW_KINDS - kinds
    text = "\n".join(every)
    for forbidden in (*secrets_to_find, code, "22222", "robinet", "présent"):
        assert forbidden and forbidden not in text


def test_un_type_inconnu_reste_refuse(user_factory):
    with pytest.raises(ValueError):
        events.notify("booking.refund", [user_factory()], "00000000-0000-0000-0000-000000000000")
