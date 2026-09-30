"""Poste de développement uniquement. Refuse de se charger avec un autre DJANGO_ENV (I1)."""

import os

from django.core.exceptions import ImproperlyConfigured

if os.environ.setdefault("DJANGO_ENV", "local") != "local":
    raise ImproperlyConfigured("settings.local exige DJANGO_ENV=local.")

from .base import *  # noqa: F403
from .base import env

DEBUG = env.bool("DEBUG", default=True)
SMS_GATEWAY = env("SMS_GATEWAY", default="fake")
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["localhost", "127.0.0.1", "api"])
# Réseau Docker Compose : le BFF local joint l'API par le réseau privé.
BFF_TRUSTED_NETWORKS = env.list("BFF_TRUSTED_NETWORKS", default=["172.16.0.0/12", "127.0.0.1/32"])
