import ast
from datetime import UTC, datetime, timedelta
from itertools import product
from pathlib import Path

import pytest
from django.db import DatabaseError, connection, transaction

import jeflink
from jeflink.bookings import services
from jeflink.bookings.machine import (
    DECLARED,
    Actor,
    Rule,
    Status,
    confirm_deadline,
    is_late,
    reliability_weight,
)
from jeflink.bookings.models import Booking, BookingEvent
from jeflink.common.errors import DomainError

from .factories import accept, make_scene

pytestmark = pytest.mark.django_db
ACTORS = [Actor.CLIENT, Actor.PRO, Actor.SYSTEM, Actor.OPS]


# --- Table des transitions : chaque couple est actif, déclaré non activé, ou interdit -----------


def classify(start, to):
    rule = DECLARED.get((start, to))
    if rule is None:
        return "forbidden"
    return "active" if rule.enabled else "not_enabled"


def test_la_machine_est_declaree_en_entier():
    declared = {status for pair in DECLARED for status in pair}
    assert declared == set(Status.values)  # de accepted à closed, annulée comprise
    # Spec 004 : tous les couples sont actifs, dont les deux annulations ajoutées.
    assert all(rule.enabled for rule in DECLARED.values())
    assert set(DECLARED) == {
        (Status.ACCEPTED, Status.SCHEDULED),
        (Status.ACCEPTED, Status.CANCELLED),
        (Status.SCHEDULED, Status.CANCELLED),
        (Status.SCHEDULED, Status.EN_ROUTE),
        (Status.EN_ROUTE, Status.ON_SITE),
        (Status.ON_SITE, Status.IN_PROGRESS),
        (Status.IN_PROGRESS, Status.IN_PROGRESS),
        (Status.IN_PROGRESS, Status.COMPLETED),
        (Status.COMPLETED, Status.CLOSED),
        (Status.COMPLETED, Status.DISPUTED),
        (Status.DISPUTED, Status.CLOSED),
        (Status.EN_ROUTE, Status.CANCELLED),
        (Status.ON_SITE, Status.CANCELLED),
        (Status.IN_PROGRESS, Status.CANCELLED),
    }


def test_acteurs_des_couples_ajoutes():
    assert DECLARED[(Status.EN_ROUTE, Status.CANCELLED)].actors == {"client", "pro", "system"}
    assert DECLARED[(Status.ON_SITE, Status.CANCELLED)].actors == {"pro", "system", "ops"}
    assert DECLARED[(Status.IN_PROGRESS, Status.CANCELLED)].actors == {"ops"}


def test_cycle_de_vie_ensembles_de_statuts():
    assert Booking.CANCELLABLE == (
        Status.ACCEPTED, Status.SCHEDULED, Status.EN_ROUTE, Status.ON_SITE
    )  # fmt: skip
    assert set(Booking.ENGAGED) == set(Status.values) - {Status.CLOSED, Status.CANCELLED}


@pytest.mark.parametrize(("start", "to"), list(product(Status.values, Status.values)))
def test_chaque_couple_de_la_machine(start, to):
    scene = make_scene(pros=1)
    booking = accept(scene)
    Booking.objects.filter(pk=booking.pk).update(
        status=start, cancelled_by="system" if start == Status.CANCELLED else ""
    )
    kind = classify(start, to)
    if kind == "forbidden":
        with pytest.raises(DomainError) as exc:
            services.transition(booking, to=to, actor=None, actor_kind=Actor.SYSTEM, reason="test")
        assert (exc.value.code, exc.value.status_code) == ("transition_not_allowed", 409)
        return
    rule = DECLARED[(start, to)]
    # Un acteur non autorisé est refusé, activé ou non.
    for actor_kind in (a for a in ACTORS if a not in rule.actors):
        with pytest.raises(DomainError) as exc:
            services.transition(booking, to=to, actor=None, actor_kind=actor_kind, reason="x")
        assert exc.value.code == "transition_not_allowed"
    actor_kind = sorted(rule.actors)[0]
    actor = {"client": scene.client, "pro": scene.providers[0].owner}.get(actor_kind)
    events_before = BookingEvent.objects.filter(booking=booking).count()
    if kind == "not_enabled":
        with pytest.raises(DomainError) as exc:
            services.transition(booking, to=to, actor=actor, actor_kind=actor_kind, reason="x")
        assert exc.value.code == "transition_not_enabled"
        assert BookingEvent.objects.filter(booking=booking).count() == events_before
        return
    services.transition(booking, to=to, actor=actor, actor_kind=actor_kind, reason="test")
    booking.refresh_from_db()
    assert booking.status == to
    # Chaque transition écrit un BookingEvent.
    event = BookingEvent.objects.filter(booking=booking).latest("id")
    assert (event.from_status, event.to_status) == (start, to)
    assert event.actor_kind == actor_kind and event.reason == "test"
    assert BookingEvent.objects.filter(booking=booking).count() == events_before + 1


def test_une_transition_systeme_n_a_pas_d_acteur_dans_le_journal():
    scene = make_scene(pros=1)
    booking = accept(scene)
    services.transition(
        booking, to=Status.CANCELLED, actor=scene.client, actor_kind=Actor.SYSTEM,
        reason="pro_unconfirmed",
    )  # fmt: skip
    assert BookingEvent.objects.filter(booking=booking).latest("id").actor is None


def test_metadonnees_d_evenement_a_schema_ferme():
    scene = make_scene(pros=1)
    booking = accept(scene)
    with pytest.raises(ValueError):
        services._write_event(
            booking, from_status="", to="x", actor=None, actor_kind="system", reason="",
            note="", metadata={"phone": "77"},
        )  # fmt: skip


def test_journal_immuable():
    scene = make_scene(pros=1)
    booking = accept(scene)
    event = BookingEvent.objects.get(booking=booking)
    event.reason = "autre"
    with pytest.raises(PermissionError):
        event.save()
    with pytest.raises(PermissionError):
        event.delete()
    with pytest.raises(PermissionError):
        BookingEvent.objects.filter(pk=event.pk).update(reason="x")
    with pytest.raises(PermissionError):
        BookingEvent.objects.filter(pk=event.pk).delete()
    BookingEvent.objects.filter(pk=event.pk).wipe_notes()  # seule exception : les notes


def test_journal_immuable_jusqu_en_base():
    scene = make_scene(pros=1)
    event = BookingEvent.objects.get(booking=accept(scene))
    for sql in (
        "UPDATE bookings_bookingevent SET reason = 'autre'",
        "UPDATE bookings_bookingevent SET note = 'x'",
        "DELETE FROM bookings_bookingevent",
    ):
        with pytest.raises(DatabaseError), transaction.atomic(), connection.cursor() as cursor:
            cursor.execute(sql)
    with connection.cursor() as cursor:  # l'effacement de la note reste permis
        cursor.execute("UPDATE bookings_bookingevent SET note = ''")
    assert BookingEvent.objects.filter(pk=event.pk).exists()


# --- Fiabilité et retard -----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("actor", "start", "to", "late", "weight"),
    [
        (Actor.PRO, Status.ACCEPTED, Status.CANCELLED, False, 0),  # avant scheduled : rien
        (Actor.PRO, Status.ACCEPTED, Status.CANCELLED, True, 0),
        (Actor.PRO, Status.SCHEDULED, Status.CANCELLED, False, 1),
        (Actor.PRO, Status.SCHEDULED, Status.CANCELLED, True, 2),
        (Actor.SYSTEM, Status.ACCEPTED, Status.CANCELLED, False, 0),  # pro_unconfirmed
        (Actor.SYSTEM, Status.SCHEDULED, Status.CANCELLED, True, 0),  # suspension
        (Actor.CLIENT, Status.ACCEPTED, Status.CANCELLED, False, 0),
        (Actor.CLIENT, Status.SCHEDULED, Status.CANCELLED, True, 0),  # tracé, sans pénalité
        (Actor.PRO, Status.ACCEPTED, Status.SCHEDULED, False, 0),
        (Actor.PRO, Status.EN_ROUTE, Status.CANCELLED, True, 2),  # parti : toujours tardif
        (Actor.PRO, Status.ON_SITE, Status.CANCELLED, True, 2),
        (Actor.CLIENT, Status.EN_ROUTE, Status.CANCELLED, True, 0),
        (Actor.SYSTEM, Status.ON_SITE, Status.CANCELLED, True, 0),  # suspension
        (Actor.PRO, Status.IN_PROGRESS, Status.IN_PROGRESS, False, 0),
    ],
)
def test_poids_de_fiabilite(actor, start, to, late, weight):
    assert (
        reliability_weight(actor_kind=actor, from_status=start, to_status=to, late=late) == weight
    )


def test_client_absent_est_trace_avec_un_poids_de_zero():
    weight = reliability_weight(
        actor_kind=Actor.PRO, from_status=Status.ON_SITE, to_status=Status.CANCELLED,
        late=True, reason="client_absent",
    )  # fmt: skip
    assert weight == 0


def test_un_couple_declare_non_active_leve_transition_not_enabled(monkeypatch):
    scene = make_scene(pros=1)
    booking = accept(scene)
    rule = Rule(frozenset({Actor.PRO}), enabled=False)
    monkeypatch.setitem(DECLARED, (Status.ACCEPTED, Status.SCHEDULED), rule)
    with pytest.raises(DomainError) as exc:
        services.transition(
            booking, to=Status.SCHEDULED, actor=scene.providers[0].owner, actor_kind=Actor.PRO,
            reason="x",
        )  # fmt: skip
    assert exc.value.code == "transition_not_enabled"


def test_annulation_tardive_a_moins_de_deux_heures():
    start = datetime(2026, 10, 5, 10, 0, tzinfo=UTC)
    assert not is_late(slot_start=start, now=start - timedelta(hours=2, minutes=1))
    assert is_late(slot_start=start, now=start - timedelta(hours=2))
    assert is_late(slot_start=start, now=start + timedelta(minutes=5))


# --- Délai de confirmation (fonction pure, heure de Dakar = UTC+0) ------------------------------

FAR = datetime(2026, 12, 1, tzinfo=UTC)


def at(hour, minute=0, day=5):
    return datetime(2026, 10, day, hour, minute, tzinfo=UTC)


@pytest.mark.parametrize(
    ("accepted", "urgent", "expected"),
    [
        (at(10), False, at(14)),  # 4 h en journée
        (at(10), True, at(11)),  # 1 h si urgente
        (at(17), False, at(21)),  # pile à l'entrée du gel
        (at(20, 30), False, at(10, 30, day=6)),  # 30 min avant le gel, 3 h 30 après 7 h
        (at(23), False, at(11, day=6)),  # en plein gel : le délai part à 7 h
        (at(23), True, at(8, day=6)),  # urgente la nuit
        (at(20, 50), True, at(7, 50, day=6)),  # 10 min avant le gel, 50 min après
        (at(6), False, at(11)),  # avant 7 h : il part à 7 h
        (at(2, day=6), True, at(8, day=6)),
        (at(21), False, at(11, day=6)),  # à 21 h pile : gelé
        (at(7), False, at(11)),  # à 7 h pile : il court
    ],
)
def test_confirm_deadline_gel_nocturne(accepted, urgent, expected):
    assert confirm_deadline(accepted_at=accepted, slot_start=FAR, urgent=urgent) == expected


def test_confirm_deadline_bornee_par_le_debut_du_creneau():
    assert confirm_deadline(accepted_at=at(10), slot_start=at(12), urgent=False) == at(12)
    assert confirm_deadline(accepted_at=at(23), slot_start=at(9, day=6), urgent=False) == at(
        9, day=6
    )


def test_confirm_deadline_reglages(settings):
    settings.BOOKING_CONFIRM_TTL = timedelta(hours=2)
    assert confirm_deadline(accepted_at=at(10), slot_start=FAR, urgent=False) == at(12)
    settings.BOOKING_CONFIRM_QUIET_HOURS = (1, 5)  # plage qui ne passe pas minuit
    settings.BOOKING_CONFIRM_TTL = timedelta(hours=4)
    assert confirm_deadline(accepted_at=at(0, 30), slot_start=FAR, urgent=False) == at(8, 30)
    assert confirm_deadline(accepted_at=at(2), slot_start=FAR, urgent=False) == at(9)
    assert confirm_deadline(accepted_at=at(10), slot_start=FAR, urgent=False) == at(14)


def test_confirm_deadline_en_heure_de_dakar_meme_avec_un_fuseau_different():
    from zoneinfo import ZoneInfo

    local = datetime(2026, 10, 5, 22, 0, tzinfo=ZoneInfo("Europe/Paris"))  # 20 h UTC
    result = confirm_deadline(accepted_at=local, slot_start=FAR, urgent=False)
    assert result == at(10, 0, day=6)  # 1 h avant le gel (UTC), 3 h après 7 h


# --- Test d'architecture : aucune écriture de statut hors de bookings/services.py ----------------

WRITES = {"update", "create", "get_or_create", "update_or_create", "bulk_create", "bulk_update"}


def _mentions_name(node: ast.AST, name: str) -> bool:
    return any(isinstance(n, ast.Name) and n.id == name for n in ast.walk(node))


def status_writes(source: str, model: str, instance_hint: str) -> list[int]:
    """Lignes où ``status`` d'un ``model`` est écrit : affectation sur une variable ou un attribut
    dont le nom contient ``instance_hint``, ``model.objects…update/create(status=…)``, ou
    ``model(status=…)``."""
    lines = []
    for node in ast.walk(ast.parse(source)):
        targets = []
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, ast.AugAssign | ast.AnnAssign):
            targets = [node.target]
        for target in targets:
            if (
                isinstance(target, ast.Attribute)
                and target.attr == "status"
                and any(
                    (isinstance(n, ast.Name) and instance_hint in n.id.lower())
                    or (isinstance(n, ast.Attribute) and instance_hint in n.attr.lower())
                    for n in ast.walk(target.value)
                )
            ):
                lines.append(node.lineno)
        if isinstance(node, ast.Call) and any(k.arg == "status" for k in node.keywords):
            func = node.func
            is_write = isinstance(func, ast.Attribute) and func.attr in WRITES
            if (is_write and _mentions_name(func, model)) or (
                isinstance(func, ast.Name) and func.id == model
            ):
                lines.append(node.lineno)
    return lines


def test_le_detecteur_d_ecriture_voit_les_ecritures_interdites():
    assert status_writes("booking.status = 'x'", "Booking", "booking") == [1]
    assert status_writes("Booking.objects.filter(pk=1).update(status='x')", "Booking", "booking")
    assert status_writes("Booking.objects.create(status='x')", "Booking", "booking")
    assert status_writes("Booking(status='x')", "Booking", "booking")
    assert status_writes("self.booking.status = 'x'", "Booking", "booking")
    # Lire ou filtrer sur le statut est permis.
    assert not status_writes("Booking.objects.filter(status='x')", "Booking", "booking")
    assert not status_writes("print(booking.status)", "Booking", "booking")


def _source_files():
    root = Path(jeflink.__file__).parent
    for path in root.rglob("*.py"):
        parts = path.relative_to(root).parts
        if "tests" in parts or "migrations" in parts:
            continue
        yield path, "/".join(parts)


def test_aucune_ecriture_du_statut_d_une_reservation_hors_de_bookings_services():
    offenders = []
    for path, name in _source_files():
        if name == "bookings/services.py":
            continue
        offenders += [
            f"{name}:{line}"
            for line in status_writes(path.read_text(encoding="utf-8"), "Booking", "booking")
        ]
    assert offenders == []


def test_aucune_ecriture_du_statut_d_une_demande_hors_de_requests_services():
    offenders = []
    for path, name in _source_files():
        if name == "requests/services.py" or not name.startswith(
            ("requests/", "bookings/", "providers/", "analytics/")
        ):
            continue
        offenders += [
            f"{name}:{line}"
            for line in status_writes(path.read_text(encoding="utf-8"), "ServiceRequest", "request")
            if name != "requests/models.py"
        ]
    assert offenders == []


def field_writes(source: str, model: str, instance_hint: str, field: str) -> list[int]:
    """Lignes où ``field`` d'un ``model`` est écrit : affectation sur une variable ou un attribut
    dont le nom contient ``instance_hint``, ou ``model.objects…update/create(field=…)``."""
    lines = []
    for node in ast.walk(ast.parse(source)):
        targets = []
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, ast.AugAssign | ast.AnnAssign):
            targets = [node.target]
        for target in targets:
            if (
                isinstance(target, ast.Attribute)
                and target.attr == field
                and any(
                    (isinstance(n, ast.Name) and instance_hint in n.id.lower())
                    or (isinstance(n, ast.Attribute) and instance_hint in n.attr.lower())
                    for n in ast.walk(target.value)
                )
            ):
                lines.append(node.lineno)
        if isinstance(node, ast.Call) and any(k.arg == field for k in node.keywords):
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr in WRITES:
                if _mentions_name(func, model):
                    lines.append(node.lineno)
            elif isinstance(func, ast.Name) and func.id == model:
                lines.append(node.lineno)
    return lines


def test_le_detecteur_d_ecriture_du_montant_voit_les_ecritures_interdites():
    assert field_writes("booking.amount_xof = 1", "Booking", "booking", "amount_xof") == [1]
    assert field_writes(
        "Booking.objects.filter(pk=1).update(amount_xof=1)", "Booking", "booking", "amount_xof"
    )
    assert field_writes("Booking(amount_xof=1)", "Booking", "booking", "amount_xof")
    assert not field_writes("print(booking.amount_xof)", "Booking", "booking", "amount_xof")
    assert not field_writes(
        "Quote.objects.create(amount_xof=1)", "Booking", "booking", "amount_xof"
    )


def test_aucune_ecriture_du_montant_d_une_reservation_hors_de_bookings_services():
    offenders = []
    for path, name in _source_files():
        if name == "bookings/services.py":
            continue
        offenders += [
            f"{name}:{line}"
            for line in field_writes(
                path.read_text(encoding="utf-8"), "Booking", "booking", "amount_xof"
            )
        ]
    assert offenders == []


def test_amount_xof_n_est_ecrit_que_par_la_creation_et_l_avenant_accepte():
    """Dans bookings/services.py même : la création, et ``accept_amendment`` (via transition)."""
    source = (Path(jeflink.__file__).parent / "bookings/services.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    writers = set()
    for func in ast.walk(tree):
        if isinstance(func, ast.FunctionDef):
            body = ast.unparse(func)
            if "amount_xof=" in body.replace(" ", "") and "Booking.objects.create" in body:
                writers.add(func.name)
            if "'amount_xof'" in body and "fields=" in body:
                writers.add(func.name)
    # ``transition`` porte le garde : amount_xof n'y passe que pour (in_progress, in_progress).
    assert writers == {"_create_from_quote", "_decide_amendment", "transition"}
