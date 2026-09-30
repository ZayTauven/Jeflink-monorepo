"""Réglages communs. Tout ce qui varie par environnement vient des variables d'environnement."""

from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parents[2]

env = environ.Env()

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
    "jeflink.accounts",
]

MIDDLEWARE = [
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
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Jeflink API",
    "DESCRIPTION": "Contrat unique des fronts et apps Jeflink (client TS généré depuis ce schéma).",
    "VERSION": "0.1.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
}

CELERY_BROKER_URL = env("REDIS_URL")
CELERY_TASK_ACKS_LATE = True
CELERY_TASK_REJECT_ON_WORKER_LOST = True
CELERY_TIMEZONE = "UTC"

# IA (côté serveur uniquement, règle 4) : modèles jamais en dur dans le code.
AI_MODEL_DEFAULT = env("AI_MODEL_DEFAULT", default="")
AI_MODEL_FAST = env("AI_MODEL_FAST", default="")

# Paiements : cash | manual_mobile_money | wiipay | fake (règle 3).
PAYMENT_GATEWAY = env("PAYMENT_GATEWAY", default="manual_mobile_money")
