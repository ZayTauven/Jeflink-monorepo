"""Réglages uniques de l'API Jeflink (démo locale).

Base SQLite dans apps/api/db.sqlite3, aucun service externe. Les variables d'environnement
permettent de durcir plus tard (voir docs/ARCHITECTURE.md › Après la démo).
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# apps/api/.env (jamais versionné), une ligne « CLE=valeur » par variable (« export » et
# commentaire « # … » en fin de ligne tolérés). Une variable déjà définie l'emporte.
if (_env := BASE_DIR / ".env").exists():
    for _line in _env.read_text(encoding="utf-8").splitlines():
        _key, _sep, _value = _line.strip().removeprefix("export ").partition("=")
        if _sep and _key.strip() and not _key.lstrip().startswith("#"):
            _value = _value.split(" #", 1)[0].strip()
            if len(_value) >= 2 and _value[0] == _value[-1] and _value[0] in "\"'":
                _value = _value[1:-1]
            os.environ.setdefault(_key.strip(), _value)

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "django-insecure-dev-only-change-me")
DEBUG = os.environ.get("DJANGO_DEBUG", "1") == "1"
ALLOWED_HOSTS = [
    "localhost",
    "127.0.0.1",
    *filter(None, os.environ.get("ALLOWED_HOSTS", "").split(",")),
]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "rest_framework.authtoken",
    "drf_spectacular",
    "jeflink.accounts",
    "jeflink.catalog",
    "jeflink.jobs",
    "jeflink.console",
    "jeflink.jef",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "jeflink.urls"
WSGI_APPLICATION = "jeflink.wsgi.application"

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

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": os.environ.get("SQLITE_PATH", BASE_DIR / "db.sqlite3"),
    }
}

AUTH_USER_MODEL = "accounts.User"
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
]

# Stockage en UTC, affichage en heure de Dakar.
LANGUAGE_CODE = "fr"
TIME_ZONE = "Africa/Dakar"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
# Images envoyées (photos de profil, images des métiers) : dossier local, servi par Django en
# développement et relayé par le site sous /media/ (voir jeflink/media.py).
MEDIA_URL = "/media/"
MEDIA_ROOT = Path(os.environ.get("MEDIA_ROOT", BASE_DIR / "media"))
# Documents des pros (pièce d'identité, attestations) : hors de MEDIA_ROOT, jamais servis tels
# quels ; lus seulement par la vue qui vérifie l'accès (le pro, l'équipe Opérations).
PRIVATE_ROOT = Path(os.environ.get("PRIVATE_ROOT", BASE_DIR / "private"))
# Tout MEDIA_ROOT est servi publiquement : les documents privés ne doivent jamais s'y trouver.
assert not PRIVATE_ROOT.resolve().is_relative_to(MEDIA_ROOT.resolve()), (
    "PRIVATE_ROOT sous MEDIA_ROOT"
)
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.TokenAuthentication",
        # Session : pour naviguer dans l'API depuis le navigateur après connexion à l'admin.
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
}

SPECTACULAR_SETTINGS = {
    "TITLE": "API Jeflink",
    "DESCRIPTION": "Démo locale : comptes, métiers, quartiers, demandes, devis et avis.",
    "VERSION": "0.1.0",
    "ENUM_NAME_OVERRIDES": {
        "RequestStatusEnum": "jeflink.jobs.models.ServiceRequest.Status",
        "QuoteStatusEnum": "jeflink.jobs.models.Quote.Status",
    },
}

# Jef, l'assistant de réservation. Sans clé d'API, Jef pose des questions fixes (mode guidé).
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
JEF_MODEL = os.environ.get("AI_MODEL_DEFAULT") or "claude-opus-5-5"
JEF_DAILY_LIMIT = 20  # échanges par client et par 24 h : chaque appel à l'IA coûte
JEF_AI_DAILY_LIMIT = 300  # échanges en IA, tous clients, par 24 h ; au-delà : mode guidé
