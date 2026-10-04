"""Crée le bucket de stockage de dev (SeaweedFS), de façon idempotente. Local seulement :

manage.py ensure_bucket
"""

from botocore.exceptions import ClientError
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from jeflink.common.storage import s3_client


class Command(BaseCommand):
    help = "Crée le bucket S3 de dev s'il n'existe pas (DJANGO_ENV=local)."

    def handle(self, *args, **options) -> None:
        if settings.DJANGO_ENV != "local":
            raise CommandError(
                "Refusé hors DJANGO_ENV=local : le bucket de production se crée à part."
            )
        if not settings.S3_ENDPOINT or not settings.S3_BUCKET:
            raise CommandError("S3_ENDPOINT et S3_BUCKET sont requis.")
        client = s3_client(endpoint=settings.S3_ENDPOINT)
        try:
            client.head_bucket(Bucket=settings.S3_BUCKET)
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") not in {"404", "NoSuchBucket", "NotFound"}:
                raise CommandError("Stockage injoignable ou refusé.") from None
            client.create_bucket(Bucket=settings.S3_BUCKET)
            self.stdout.write(f"Bucket créé : {settings.S3_BUCKET}")
            return
        self.stdout.write(f"Bucket présent : {settings.S3_BUCKET}")
