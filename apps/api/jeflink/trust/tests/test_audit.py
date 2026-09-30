import threading
import time
import uuid

import pytest
from django.db import IntegrityError, connection, connections, transaction
from django.db.utils import DatabaseError

from jeflink.accounts.models import User
from jeflink.common.pii import mask_phone, phone_hmac
from jeflink.trust.models import AuditEvent
from jeflink.trust.services import (
    AUDIT_METADATA_SCHEMAS,
    AuditSchemaError,
    MaskedPhone,
    PhoneHmac,
    audit,
    register_audit_schema,
)

ACTION = "test.thing.done"


@pytest.fixture(autouse=True)
def schema_de_test():
    register_audit_schema(
        ACTION,
        {
            "count": int,
            "label": str,
            "ok": bool,
            "phone_masked": MaskedPhone,
            "phone_hmac": PhoneHmac,
            "groups": list,
            "ref": str,
        },
    )
    yield
    AUDIT_METADATA_SCHEMAS.pop(ACTION, None)


@pytest.mark.django_db
def test_audit_systeme_sans_acteur():
    event = audit(action=ACTION, metadata={"count": 2})
    assert event.actor_kind == "system"
    assert AuditEvent.objects.get().metadata == {"count": 2}


@pytest.mark.django_db
def test_acteur_identifie_par_public_id(user_factory):
    user = user_factory()
    event = audit(action=ACTION, actor=user)
    assert event.actor_id == user.pk
    assert event.actor_public_id == user.public_id


@pytest.mark.django_db
def test_valeurs_pseudonymisees_acceptees():
    for i in range(300):
        audit(
            action=ACTION,
            metadata={
                "phone_masked": mask_phone(f"+22177{i:07d}"),
                "phone_hmac": phone_hmac(f"+22177{i:07d}"),
                "ref": str(uuid.uuid4()),
            },
        )


@pytest.mark.django_db
@pytest.mark.parametrize(
    "metadata",
    [
        {"inconnue": 1},
        {"count": "2"},
        {"count": True},
        {"label": "+221771234567"},
        {"label": "appeler 77 123 45 67"},
        {"label": "x" * 281},
        {"phone_masked": "+221771234567"},
        {"phone_hmac": "pas-un-hmac"},
        {"groups": ["Support", "77 123 45 67"]},
    ],
)
def test_metadonnees_refusees(metadata):
    with pytest.raises(AuditSchemaError):
        audit(action=ACTION, metadata=metadata)
    assert not AuditEvent.objects.exists()


@pytest.mark.django_db
def test_metadonnees_trop_volumineuses():
    with pytest.raises(AuditSchemaError, match="volumineuses"):
        audit(action=ACTION, metadata={"groups": ["x" * 200] * 30})


@pytest.mark.django_db
def test_action_non_declaree_refusee():
    with pytest.raises(AuditSchemaError):
        audit(action="jamais.declaree")


@pytest.mark.django_db
def test_ajout_seul_cote_application():
    event = audit(action=ACTION)
    with pytest.raises(PermissionError):
        event.save()
    with pytest.raises(PermissionError):
        event.delete()
    with pytest.raises(PermissionError):
        AuditEvent.objects.update(action="x")
    with pytest.raises(PermissionError):
        AuditEvent.objects.all().delete()
    # Un objet neuf portant la clé primaire d'un autre ne l'écrase pas : INSERT forcé.
    with pytest.raises(IntegrityError), transaction.atomic():
        AuditEvent(pk=event.pk, actor_kind="system", action=ACTION).save()


@pytest.mark.django_db
def test_ajout_seul_cote_base():
    event = audit(action=ACTION)
    with (
        pytest.raises(DatabaseError, match="ajout seul"),
        transaction.atomic(),
        connection.cursor() as cursor,
    ):
        cursor.execute("UPDATE trust_auditevent SET action = 'x' WHERE id = %s", [event.pk])
    with (
        pytest.raises(DatabaseError, match="ajout seul"),
        transaction.atomic(),
        connection.cursor() as cursor,
    ):
        cursor.execute("DELETE FROM trust_auditevent WHERE id = %s", [event.pk])


@pytest.mark.django_db
def test_action_utilisateur_sans_acteur_refusee():
    with pytest.raises(IntegrityError), transaction.atomic():
        audit(action=ACTION, actor_kind="user")


@pytest.mark.django_db
def test_action_ops_de_commande_sans_compte_acceptee():
    assert audit(action=ACTION, actor_kind="ops").actor_public_id is None


# Tests transactionnels : pytest-django les place en fin de passage ; serialized_rollback
# restaure les données de migration (groupes Ops) vidées par un flush précédent.
@pytest.mark.django_db(transaction=True, databases="__all__", serialized_rollback=True)
def test_audit_durable_survit_au_rollback():
    with pytest.raises(RuntimeError), transaction.atomic():
        audit(action=ACTION, metadata={"count": 1})
        audit(action=ACTION, metadata={"count": 2}, durable=True)
        raise RuntimeError("échec métier")
    assert list(AuditEvent.objects.values_list("metadata", flat=True)) == [{"count": 2}]


@pytest.mark.django_db(transaction=True, databases="__all__", serialized_rollback=True)
def test_audit_durable_avec_acteur_verrouille_et_cree_dans_la_transaction():
    """Acteur créé puis verrouillé FOR UPDATE par l'appelant : l'audit durable ne bloque pas."""
    result: dict = {}

    def run():
        try:
            with pytest.raises(RuntimeError), transaction.atomic():
                user = User.objects.create_user("+221771234567")
                User.objects.select_for_update().get(pk=user.pk)
                started = time.monotonic()
                result["event"] = audit(action=ACTION, actor=user, durable=True)
                result["seconds"] = time.monotonic() - started
                raise RuntimeError("échec après audit")
        finally:
            connections.close_all()  # connexions propres au thread

    worker = threading.Thread(target=run)
    worker.start()
    worker.join(timeout=10)
    assert not worker.is_alive(), "l'audit durable est resté bloqué"
    assert result["seconds"] < 2
    event = AuditEvent.objects.get()
    assert event.actor_id is None
    assert event.actor_public_id == result["event"].actor_public_id
