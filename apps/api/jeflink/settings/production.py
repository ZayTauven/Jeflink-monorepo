"""Réglages de staging et de production : réglages par défaut de tous les points d'entrée."""

from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F403
from .base import DJANGO_ENV, env

if DJANGO_ENV not in {"staging", "production"}:
    raise ImproperlyConfigured(
        f"settings.production exige DJANGO_ENV=staging ou production (reçu : {DJANGO_ENV})."
    )

# Redis de limitation dédié et sans éviction (S7) : obligatoire, distinct du cache et du broker.
RATELIMIT_REDIS_URL = env("RATELIMIT_REDIS_URL")
if RATELIMIT_REDIS_URL in {env("REDIS_URL"), env("REDIS_CACHE_URL", default="")}:
    raise ImproperlyConfigured("RATELIMIT_REDIS_URL doit viser une base Redis dédiée.")
BFF_TRUSTED_NETWORKS = env.list("BFF_TRUSTED_NETWORKS")
# Sans hachage, pas de remplissage automatique du code sur Android (spec 001, T3).
if not all(SMS_ANDROID_APP_HASH.values()):  # noqa: F405
    raise ImproperlyConfigured("SMS_ANDROID_APP_HASH_CLIENT et _PRO sont obligatoires.")

DEBUG = False
SERVE_API_SCHEMA = False

# Derrière le reverse proxy TLS.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=True)
SECURE_HSTS_SECONDS = env.int("SECURE_HSTS_SECONDS", default=60 * 60 * 24 * 365)
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "no-referrer"
SESSION_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_SECURE = True
X_FRAME_OPTIONS = "DENY"
