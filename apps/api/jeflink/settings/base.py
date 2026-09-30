"""Réglages communs. Tout ce qui varie par environnement vient des variables d'environnement."""

from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parents[2]

env = environ.Env()

# local | test | staging | production. Par défaut le plus strict.
DJANGO_ENVS = frozenset({"local", "test", "staging", "production"})
DJANGO_ENV = env("DJANGO_ENV", default="production")

SECRET_KEY = env("SECRET_KEY")
DEBUG = env.bool("DEBUG", default=False)
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=[])

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.gis",
    "rest_framework",
    "drf_spectacular",
    # Domaines Jeflink (un par app, voir apps/api/CLAUDE.md)
    "jeflink.common",
    "jeflink.trust",
    "jeflink.notifications",
    "jeflink.accounts",
]

MIDDLEWARE = [
    "jeflink.common.request_context.RequestIdMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "jeflink.urls"
WSGI_APPLICATION = "jeflink.wsgi.application"
ASGI_APPLICATION = "jeflink.asgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

# PostGIS obligatoire (zones en polygones, distances réelles) : DATABASE_URL en postgis://
DATABASES = {"default": env.db("DATABASE_URL")}
DATABASES["default"]["CONN_MAX_AGE"] = env.int("DB_CONN_MAX_AGE", default=60)
DATABASES["default"]["CONN_HEALTH_CHECKS"] = True
# Seconde connexion vers la même base : les AuditEvent d'un chemin d'erreur y sont écrits
# hors de la transaction appelante, pour survivre à son rollback (spec 001 S15).
# Délais courts : un audit durable ne doit jamais bloquer la requête qui l'écrit.
DATABASES["audit"] = {
    **DATABASES["default"],
    "OPTIONS": {"options": "-c lock_timeout=2000 -c statement_timeout=5000"},
    "TEST": {"MIRROR": "default"},
}
DATABASE_ROUTERS = ["jeflink.common.db_routers.AuditConnectionRouter"]
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

AUTH_USER_MODEL = "accounts.User"
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# Dates stockées en UTC, affichées en Africa/Dakar (règle 5).
USE_TZ = True
TIME_ZONE = env("TIME_ZONE", default="Africa/Dakar")
USE_I18N = True
LANGUAGE_CODE = "fr"
# « wo » sera ajouté avec ses traductions (Django ne fournit pas de locale wolof).
LANGUAGES = [("fr", "Français")]

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

REST_FRAMEWORK = {
    # Sécurisé par défaut : chaque vue publique le déclare explicitement.
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_AUTHENTICATION_CLASSES": ["rest_framework.authentication.SessionAuthentication"],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_PAGINATION_CLASS": "jeflink.common.pagination.CreatedCursorPagination",
    "PAGE_SIZE": 20,
    "EXCEPTION_HANDLER": "jeflink.common.api.exceptions.exception_handler",
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Jeflink API",
    "DESCRIPTION": "Contrat unique des fronts et apps Jeflink (client TS généré depuis ce schéma).",
    "VERSION": "0.1.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
}

REDIS_URL = env("REDIS_URL")

# Cache partagé entre workers : indispensable aux limites de débit (spec 001).
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": env("REDIS_CACHE_URL", default=REDIS_URL),
        "KEY_PREFIX": "jf",
    }
}

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {"pii": {"()": "jeflink.common.log_filters.PiiRedactingFilter"}},
    "formatters": {
        "plain": {"format": "%(asctime)s %(levelname)s %(name)s %(message)s"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "filters": ["pii"], "formatter": "plain"},
    },
    "root": {"handlers": ["console"], "level": env("LOG_LEVEL", default="INFO")},
    # Les loggers Django gardent leur propre propagation : on les rattache au handler filtré.
    "loggers": {
        "django": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "django.server": {"handlers": ["console"], "level": "INFO", "propagate": False},
    },
}

# Secrets applicatifs (spec 001 S21) : présents, ≥ 32 octets, distincts entre eux et de SECRET_KEY.
# Vérifiés au démarrage par jeflink.common.secrets. Rotation : plusieurs valeurs acceptées.
# JWT_SIGNING_KEYS = "kid1:clé1,kid2:clé2" ; la première est la clé active.
JWT_SIGNING_KEYS_RAW = env.list("JWT_SIGNING_KEYS", default=[])
JWT_SIGNING_KEYS = dict(item.split(":", 1) for item in JWT_SIGNING_KEYS_RAW if ":" in item)
OTP_HMAC_KEY = env("OTP_HMAC_KEY", default="")
MFA_ENCRYPTION_KEYS = env.list("MFA_ENCRYPTION_KEYS", default=[])
BFF_SHARED_SECRETS = env.list("BFF_SHARED_SECRETS", default=[])
PII_HMAC_KEY = env("PII_HMAC_KEY", default="")

# Schéma OpenAPI servi seulement en local/test ; `make openapi` le génère hors ligne (S24).
SERVE_API_SCHEMA = DJANGO_ENV in {"local", "test"}

CELERY_BROKER_URL = REDIS_URL
# Celery garde la configuration LOGGING (et son filtre de données personnelles) : voir celery.py.
CELERY_WORKER_HIJACK_ROOT_LOGGER = False
CELERY_TASK_ACKS_LATE = True
CELERY_TASK_REJECT_ON_WORKER_LOST = True
CELERY_TIMEZONE = "UTC"

# IA (côté serveur uniquement, règle 4) : modèles jamais en dur dans le code.
AI_MODEL_DEFAULT = env("AI_MODEL_DEFAULT", default="")
AI_MODEL_FAST = env("AI_MODEL_FAST", default="")

# SMS (ADR 0008) : adaptateur obligatoire hors local/test ; « fake » y est interdit (S23).
SMS_GATEWAY = env("SMS_GATEWAY", default="")
SMS_SENDER_ID = env("SMS_SENDER_ID", default="JEFLINK")

# Paiements : cash | manual_mobile_money | wiipay | fake (règle 3).
PAYMENT_GATEWAY = env("PAYMENT_GATEWAY", default="manual_mobile_money")
