"""Écriture des AuditEvent. Chaque action déclare le schéma fermé de ses métadonnées (S15)."""

import json
import re
from typing import Any, Protocol

from django.db import models, transaction

from jeflink.common.pii import MASKED_PHONE_RE, PHONE_HMAC_RE, contains_pii
from jeflink.common.request_context import current_request_id

from .models import AuditEvent

MAX_STRING = 280
MAX_METADATA_BYTES = 4096


class PseudonymizedField:
    """Marqueur de schéma : valeur déjà pseudonymisée, contrôlée par motif strict."""

    pattern: re.Pattern[str]


class PhoneHmac(PseudonymizedField):
    pattern = PHONE_HMAC_RE


class MaskedPhone(PseudonymizedField):
    pattern = MASKED_PHONE_RE


FieldType = type | tuple[type, ...]

# action -> {clé: type(s) autorisé(s)}. Chaque domaine enregistre ses actions dans son ready().
AUDIT_METADATA_SCHEMAS: dict[str, dict[str, FieldType]] = {}


class AuditSchemaError(ValueError):
    pass


class HasPublicId(Protocol):
    public_id: Any
    _meta: Any


def register_audit_schema(action: str, fields: dict[str, FieldType]) -> None:
    if action in AUDIT_METADATA_SCHEMAS and AUDIT_METADATA_SCHEMAS[action] != fields:
        raise AuditSchemaError(f"schéma déjà enregistré différemment pour {action}")
    AUDIT_METADATA_SCHEMAS[action] = fields


def _check_free_value(action: str, key: str, value: Any) -> None:
    """Contrôle récursif d'une valeur libre : ni donnée personnelle, ni chaîne trop longue."""
    if isinstance(value, str):
        if len(value) > MAX_STRING or contains_pii(value):
            raise AuditSchemaError(f"{action} : valeur refusée pour « {key} »")
    elif isinstance(value, dict):
        for sub_key, sub_value in value.items():
            _check_free_value(action, key, str(sub_key))
            _check_free_value(action, key, sub_value)
    elif isinstance(value, list | tuple):
        for item in value:
            _check_free_value(action, key, item)


def _validate(action: str, metadata: dict[str, Any]) -> None:
    schema = AUDIT_METADATA_SCHEMAS.get(action)
    if schema is None:
        raise AuditSchemaError(f"action d'audit non déclarée : {action}")
    for key, value in metadata.items():
        if key not in schema:
            raise AuditSchemaError(f"{action} : clé non déclarée « {key} »")
        allowed = schema[key] if isinstance(schema[key], tuple) else (schema[key],)
        markers = [t for t in allowed if isinstance(t, type) and issubclass(t, PseudonymizedField)]
        if markers:
            if not (isinstance(value, str) and any(m.pattern.match(value) for m in markers)):
                raise AuditSchemaError(f"{action} : valeur non pseudonymisée pour « {key} »")
            continue
        # bool est un int en Python : on l'exclut sauf s'il est demandé explicitement.
        if isinstance(value, bool) and bool not in allowed:
            raise AuditSchemaError(f"{action} : type invalide pour « {key} »")
        if value is not None and not isinstance(value, allowed):
            raise AuditSchemaError(f"{action} : type invalide pour « {key} »")
        _check_free_value(action, key, value)
    if len(json.dumps(metadata, default=str).encode()) > MAX_METADATA_BYTES:
        raise AuditSchemaError(f"{action} : métadonnées trop volumineuses")


def audit(
    *,
    action: str,
    actor: models.Model | None = None,
    actor_kind: str | None = None,
    target: HasPublicId | None = None,
    metadata: dict[str, Any] | None = None,
    session_public_id: Any = None,
    durable: bool = False,
) -> AuditEvent:
    """Écrit un AuditEvent.

    ``durable=True`` : écrit sur la connexion ``audit``, hors de la transaction appelante,
    pour survivre à son rollback (verrouillage, réutilisation de refresh…). Aucune clé
    étrangère n'est alors posée : l'acteur est identifié par ``actor_public_id``.
    """
    metadata = metadata or {}
    _validate(action, metadata)
    if actor_kind is None:
        actor_kind = AuditEvent.ActorKind.USER if actor else AuditEvent.ActorKind.SYSTEM
    event = AuditEvent(
        actor_id=actor.pk if actor is not None and not durable else None,
        actor_public_id=getattr(actor, "public_id", None),
        actor_kind=actor_kind,
        action=action,
        target_type=target._meta.label_lower if target is not None else "",
        target_public_id=target.public_id if target is not None else None,
        session_public_id=session_public_id,
        request_id=current_request_id(),
        metadata=metadata,
    )
    if durable:
        with transaction.atomic(using="audit"):
            event.save(using="audit")
    else:
        event.save()
    return event
