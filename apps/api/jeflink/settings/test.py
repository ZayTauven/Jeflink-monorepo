import os

# Les tests tournent dans le conteneur api (PostGIS réel) ; valeurs par défaut pour le reste.
os.environ.setdefault("SECRET_KEY", "test-only-not-secret")
os.environ.setdefault("REDIS_URL", "redis://redis:6379/15")

from .base import *  # noqa: F403

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
CELERY_TASK_ALWAYS_EAGER = True
PAYMENT_GATEWAY = "fake"
