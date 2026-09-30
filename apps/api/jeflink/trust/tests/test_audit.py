import pytest
from django.db import transaction

from jeflink.common.pii import mask_phone
from jeflink.trust.models import AuditEvent
from jeflink.trust.services import (
    AUDIT_METADATA_SCHEMAS,
    AuditSchemaError,
    audit,
    register_audit_schema,
)

ACTION = "test.thing.done"


@pytest.fixture(autouse=True)
def schema_de_test():
    register_audit_schema(ACTION, {"count": int, "phone_masked": str, "ok": bool})
    yield
    AUDIT_METADATA_SCHEMAS.pop(ACTION, None)


@pytest.mark.django_db
def test_audit_systeme_sans_acteur():
    event = audit(action=ACTION, metadata={"count": 2})
    assert event.actor_kind == "system"
    assert AuditEvent.objects.get().metadata == {"count": 2}


@pytest.mark.django_db
def test_numero_masque_accepte():
    audit(action=ACTION, metadata={"phone_masked": mask_phone("+221771234567")})


@pytest.mark.django_db
@pytest.mark.parametrize(
    "metadata",
    [
        {"inconnue": 1},
        {"count": "2"},
        {"count": True},
        {"phone_masked": "+221771234567"},
        {"phone_masked": "77 123 45 67"},
    ],
)
def test_metadonnees_refusees(metadata):
    with pytest.raises(AuditSchemaError):
        audit(action=ACTION, metadata=metadata)
    assert not AuditEvent.objects.exists()


@pytest.mark.django_db
def test_action_non_declaree_refusee():
    with pytest.raises(AuditSchemaError):
        audit(action="jamais.declaree")


@pytest.mark.django_db
def test_ajout_seul():
    event = audit(action=ACTION)
    with pytest.raises(PermissionError):
        event.save()
    with pytest.raises(PermissionError):
        event.delete()


# Test transactionnel : pytest-django le place en fin de passage ; serialized_rollback
# restaure les données de migration (groupes Ops) vidées par un flush précédent.
@pytest.mark.django_db(transaction=True, databases="__all__", serialized_rollback=True)
def test_audit_durable_survit_au_rollback():
    with pytest.raises(RuntimeError), transaction.atomic():
        audit(action=ACTION, metadata={"count": 1})
        audit(action=ACTION, metadata={"count": 2}, durable=True)
        raise RuntimeError("échec métier")
    assert list(AuditEvent.objects.values_list("metadata", flat=True)) == [{"count": 2}]


@pytest.mark.django_db
def test_action_utilisateur_sans_acteur_refusee():
    from django.db import IntegrityError

    with pytest.raises(IntegrityError), transaction.atomic():
        audit(action=ACTION, actor_kind="user")


@pytest.mark.django_db
def test_action_ops_de_commande_sans_compte_acceptee():
    assert audit(action=ACTION, actor_kind="ops").actor_id is None
