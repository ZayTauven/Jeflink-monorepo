"""Stockage d'objets (ADR 0011) : un bucket privé, des clés faites de ``public_id`` seulement,
des URL signées courtes. Aucune URL publique permanente.

Le stockage nommé ``photos`` est S3 (SeaweedFS en dev) ; en test, ``InMemoryStorage`` : aucun
réseau. Les écritures passent par ``put`` (jamais de renommage silencieux si la clé existe).
"""

import time
from urllib.parse import quote

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import Storage, storages

PHOTOS = "photos"


def photos_storage() -> Storage:
    return storages[PHOTOS]


def _is_s3(storage: Storage) -> bool:
    from storages.backends.s3 import S3Storage

    return isinstance(storage, S3Storage)


def put(key: str, content: bytes, *, storage: Storage | None = None) -> None:
    """Écrit un objet sous ``key`` (remplace s'il existe)."""
    storage = storage or photos_storage()
    if storage.exists(key):
        storage.delete(key)
    saved = storage.save(key, ContentFile(content))
    if saved != key:
        storage.delete(saved)
        raise RuntimeError("clé d'objet modifiée par le stockage")


def read(key: str, *, storage: Storage | None = None) -> bytes:
    with (storage or photos_storage()).open(key, "rb") as handle:
        return handle.read()


def exists(key: str, *, storage: Storage | None = None) -> bool:
    return bool(key) and (storage or photos_storage()).exists(key)


def delete(key: str, *, storage: Storage | None = None) -> None:
    """Supprime un objet ; absent, ce n'est pas une erreur (idempotent)."""
    if key:
        (storage or photos_storage()).delete(key)


def s3_client(*, endpoint: str):
    import boto3
    from botocore.config import Config

    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=settings.S3_ACCESS_KEY or "unset",
        aws_secret_access_key=settings.S3_SECRET_KEY or "unset",
        region_name=settings.S3_REGION,
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )


def signed_url(key: str, *, expires_in: int | None = None, storage: Storage | None = None) -> str:
    """URL de lecture signée, valable ``BOOKING_PHOTO_URL_TTL`` secondes (10 min).

    Signée pour l'hôte que voit le navigateur (``S3_PUBLIC_ENDPOINT``), pas l'hôte interne.
    Hors S3 (test), une URL factice qui porte la clé et l'échéance.
    """
    ttl = expires_in or settings.BOOKING_PHOTO_URL_TTL
    storage = storage or photos_storage()
    if not _is_s3(storage):
        return (
            f"{settings.S3_PUBLIC_ENDPOINT}/{quote(key)}?expires={int(time.time()) + ttl}&sig=test"
        )
    client = s3_client(endpoint=settings.S3_PUBLIC_ENDPOINT or settings.S3_ENDPOINT)
    return client.generate_presigned_url(
        "get_object", Params={"Bucket": settings.S3_BUCKET, "Key": key}, ExpiresIn=ttl
    )
