"""Stockage d'objets (ADR 0011) : clés sans collision silencieuse, URL signées, secrets, bucket."""

from urllib.parse import parse_qs, urlparse

import pytest
from botocore.exceptions import ClientError
from django.core.exceptions import ImproperlyConfigured
from django.core.management import call_command
from django.core.management.base import CommandError

from jeflink.common import storage
from jeflink.common.secrets import check_secrets, secret_problems

COMMAND = "jeflink.common.management.commands.ensure_bucket.s3_client"


def test_put_remplace_sans_renommer():
    storage.put("bookings/a/b.webp", b"un")
    storage.put("bookings/a/b.webp", b"deux")
    assert storage.read("bookings/a/b.webp") == b"deux"
    assert not storage.exists("bookings/a/b_abc123.webp")


def test_delete_est_idempotent():
    storage.put("k.webp", b"x")
    storage.delete("k.webp")
    storage.delete("k.webp")
    storage.delete("")
    assert not storage.exists("k.webp")


def test_url_signee_de_test_porte_la_cle_et_l_echeance(settings):
    settings.BOOKING_PHOTO_URL_TTL = 600
    url = urlparse(storage.signed_url("bookings/x/y.webp"))
    assert url.netloc == "storage.test" and url.path == "/bookings/x/y.webp"
    assert "expires" in parse_qs(url.query)


def test_url_signee_s3_est_signee_pour_l_hote_public(settings):
    """Le client boto3 signe pour ``S3_PUBLIC_ENDPOINT``, sans aucun appel réseau."""
    from storages.backends.s3 import S3Storage

    settings.S3_PUBLIC_ENDPOINT = "http://localhost:8333"
    settings.S3_ENDPOINT = "http://s3:8333"
    settings.S3_BUCKET = "jeflink-dev"
    s3 = S3Storage(bucket_name="jeflink-dev", access_key="a", secret_key="b")
    url = storage.signed_url("bookings/x/y.webp", expires_in=600, storage=s3)
    parsed = urlparse(url)
    assert parsed.netloc == "localhost:8333"
    assert parsed.path == "/jeflink-dev/bookings/x/y.webp"
    query = parse_qs(parsed.query)
    assert query["X-Amz-Expires"] == ["600"] and "X-Amz-Signature" in query


def test_ensure_bucket_refuse_hors_local():
    with pytest.raises(CommandError):
        call_command("ensure_bucket")  # DJANGO_ENV=test


def test_ensure_bucket_cree_puis_reconnait(settings, monkeypatch, capsys):
    settings.DJANGO_ENV = "local"
    settings.S3_ENDPOINT, settings.S3_BUCKET = "http://s3:8333", "jeflink-dev"
    created = []

    class FakeClient:
        def head_bucket(self, Bucket):
            if not created:
                raise ClientError({"Error": {"Code": "404"}}, "HeadBucket")

        def create_bucket(self, Bucket):
            created.append(Bucket)

    monkeypatch.setattr(COMMAND, lambda endpoint: FakeClient())
    call_command("ensure_bucket")
    call_command("ensure_bucket")
    assert created == ["jeflink-dev"]  # la deuxième fois, rien à créer
    assert "Bucket présent" in capsys.readouterr().out


def test_ensure_bucket_ne_cache_pas_un_refus(settings, monkeypatch):
    settings.DJANGO_ENV = "local"
    settings.S3_ENDPOINT, settings.S3_BUCKET = "http://s3:8333", "jeflink-dev"

    class Refusing:
        def head_bucket(self, Bucket):
            raise ClientError({"Error": {"Code": "403"}}, "HeadBucket")

    monkeypatch.setattr(COMMAND, lambda endpoint: Refusing())
    with pytest.raises(CommandError):
        call_command("ensure_bucket")


# --- Contrôle au démarrage ---------------------------------------------------------------------


def test_stockage_non_controle_en_test():
    assert secret_problems() == []


@pytest.mark.parametrize("env", ["staging", "production"])
def test_stockage_incomplet_refuse_hors_local(settings, env):
    settings.DJANGO_ENV = env
    settings.S3_ENDPOINT = settings.S3_BUCKET = settings.S3_ACCESS_KEY = ""
    problems = secret_problems()
    assert any(p.startswith("S3_BUCKET") for p in problems)
    assert any(p.startswith("S3_ACCESS_KEY") for p in problems)
    with pytest.raises(ImproperlyConfigured, match="S3_BUCKET"):
        check_secrets()


def test_hote_public_en_clair_et_identifiants_de_dev_refuses_hors_local(settings):
    settings.DJANGO_ENV = "production"
    settings.S3_ENDPOINT = "https://s3.interne"
    settings.S3_PUBLIC_ENDPOINT = "http://cdn.example"
    settings.S3_BUCKET = "jeflink"
    settings.S3_ACCESS_KEY = "local-dev-s3-access-not-secret"
    settings.S3_SECRET_KEY = "z" * 40
    problems = secret_problems()
    assert any("HTTPS" in p for p in problems)
    assert any(p.startswith("S3_ACCESS_KEY") and "publique" in p for p in problems)
    assert not any(p.startswith("S3_SECRET_KEY") for p in problems)
