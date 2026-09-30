"""Écriture des AuditEvent. Chaque action déclare le schéma fermé de ses métadonnées (S15)."""

from typing import Any, Protocol

from django.db import models, transaction

from jeflink.common.pii import contains_pii
from jeflink.common.request_context import current_request_id

from .models import AuditEvent

# action -> {clé: type(s) autorisé(s)}. Chaque domaine enregistre ses actions dans son ready().
AUDIT_METADATA_SCHEMAS: dict[str, dict[str, type | tuple[type, ...]]] = {}


class AuditSchemaError(ValueError):
    pass


class HasPublicId(Protocol):
    public_id: Any
    _meta: Any


def register_audit_schema(action: str, fields: dict[str, type | tuple[type, ...]]) -> None:
    if action in AUDIT_METADATA_SCHEMAS and AUDIT_METADATA_SCHEMAS[action] != fields:
        raise AuditSchemaError(f"schéma déjà enregistré différemment pour {action}")
    AUDIT_METADATA_SCHEMAS[action] = fields


def _validate(action: str, metadata: dict[str, Any]) -> None:
    schema = AUDIT_METADATA_SCHEMAS.get(action)
    if schema is None:
        raise AuditSchemaError(f"action d'audit non déclarée : {action}")
    for key, value in metadata.items():
        if key not in schema:
            raise AuditSchemaError(f"{action} : clé non déclarée « {key} »")
        # bool est un int en Python : on l'exclut sauf s'il est demandé explicitement.
        allowed = schema[key] if isinstance(schema[key], tuple) else (schema[key],)
        if isinstance(value, bool) and bool not in allowed:
            raise AuditSchemaError(f"{action} : type invalide pour « {key} »")
        if value is not None and not isinstance(value, allowed):
            raise AuditSchemaError(f"{action} : type invalide pour « {key} »")
        # Les numéros masqués (mask_phone) et HMAC ne sont pas détectés ; un numéro en clair l'est.
        if isinstance(value, str) and contains_pii(value):
            raise AuditSchemaError(f"{action} : donnée personnelle dans « {key} »")


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

    ``durable=True`` : écrit sur la connexion ``audit``, hors de la transaction appelante ;
    à utiliser sur les chemins d'erreur (verrouillage, réutilisation de refresh…).
    """
    metadata = metadata or {}
    _validate(action, metadata)
    if actor_kind is None:
        actor_kind = AuditEvent.ActorKind.USER if actor else AuditEvent.ActorKind.SYSTEM
    event = AuditEvent(
        actor_id=actor.pk if actor else None,
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
