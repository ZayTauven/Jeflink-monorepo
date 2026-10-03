"""Réglages communs. Tout ce qui varie par environnement vient des variables d'environnement."""

from datetime import timedelta
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
    # Admin Django avec second facteur et limite de débit (tâche 21).
    "jeflink.admin_config.JeflinkAdminConfig",
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
    "jeflink.catalog",
    "jeflink.zones",
    "jeflink.providers",
    "jeflink.analytics",
    "jeflink.requests",
    "jeflink.bookings",
]

MIDDLEWARE = [
    "jeflink.common.request_context.RequestIdMiddleware",
    "jeflink.common.client_ip.TrustedClientIpMiddleware",
    "jeflink.common.request_context.NoStoreMiddleware",
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
    # IsClient refuse aussi les comptes techniques et les sessions restreintes (S3, S18).
    "DEFAULT_PERMISSION_CLASSES": ["jeflink.accounts.permissions.IsClient"],
    # Bearer JWT seulement (ADR 0007) : ni session, ni CSRF côté API.
    "DEFAULT_AUTHENTICATION_CLASSES": ["jeflink.accounts.authentication.SessionJWTAuthentication"],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_PAGINATION_CLASS": "jeflink.common.pagination.CreatedCursorPagination",
    "PAGE_SIZE": 20,
    "EXCEPTION_HANDLER": "jeflink.common.api.exceptions.exception_handler",
    # Limites par IP déclarées par vue (rate_limit_scope) ; voir IP_RATE_LIMITS.
    "DEFAULT_THROTTLE_CLASSES": ["jeflink.common.api.throttling.IpRateThrottle"],
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Jeflink API",
    "DESCRIPTION": "Contrat unique des fronts et apps Jeflink (client TS généré depuis ce schéma).",
    "VERSION": "0.1.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
    # Noms stables des énumérations de la demande, des devis et des réservations (client TS).
    "ENUM_NAME_OVERRIDES": {
        "RequestStatusEnum": "jeflink.requests.models.ServiceRequest.Status",
        "QuoteStatusEnum": "jeflink.requests.models.Quote.Status",
        "QuoteKindEnum": "jeflink.requests.models.Quote.Kind",
        "PreferredWhenEnum": "jeflink.requests.models.ServiceRequest.When",
        "PreferredPeriodEnum": "jeflink.requests.models.ServiceRequest.Period",
        "QuoteLineKindEnum": "jeflink.requests.models.QuoteLine.Kind",
        "BookingStatusEnum": "jeflink.bookings.models.Booking.Status",
        "ProviderStatusEnum": "jeflink.providers.models.Provider.Status",
    },
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

# --- Limites de débit (spec 001, « Limites de débit ») ---------------------------------
# Redis dédié à l'auth en production (noeviction, tâche infra 2).
RATELIMIT_REDIS_URL = env("RATELIMIT_REDIS_URL", default=env("REDIS_CACHE_URL", default=REDIS_URL))
AUTH_REDIS_PRIVATE_HOSTS: list[str] = []
AUTH_REDIS_NOEVICTION_ATTESTED = env.bool("AUTH_REDIS_NOEVICTION_ATTESTED", default=False)
# IP exactes des reverse proxies dont uvicorn reprend X-Forwarded-For (contrôle common.E30x).
FORWARDED_ALLOW_IPS = env.list("FORWARDED_ALLOW_IPS", default=[])
# Le BFF ne peut fixer l'IP cliente que depuis un réseau interne déclaré, par un hôte interne,
# avec le secret (S9). Par défaut, aucun réseau n'est de confiance.
INTERNAL_API_HOSTS = env.list("INTERNAL_API_HOSTS", default=["api"])
BFF_TRUSTED_NETWORKS = env.list("BFF_TRUSTED_NETWORKS", default=[])
# Par IP, larges à cause du CGNAT des opérateurs mobiles. fail_open : seulement la sonde.
IP_RATE_LIMITS = {
    "health": {"limit": 120, "window": 60, "fail_open": True},
    "api_docs": {"limit": 60, "window": 60, "fail_open": True},  # local/test seulement
    "auth_config": {"limit": 120, "window": 60},
    "otp_request": {"limit": 30, "window": 600},
    "otp_verify": {"limit": 60, "window": 600},
    # Large : derrière le CGNAT d'un opérateur, des centaines d'utilisateurs partagent une IP.
    # Forcer un refresh de 256 bits est de toute façon impossible (revue sécu tâche 8, M7).
    "token_refresh": {"limit": 300, "window": 60},
    "token_revoke": {"limit": 300, "window": 60},  # CGNAT : des centaines de clients par IP
    "phone_change_confirm": {"limit": 20, "window": 600},
    # Second facteur Ops : le vrai verrou est par jeton (5 essais) et par compte (10/24 h).
    "mfa": {"limit": 30, "window": 600},
    "mfa_step_up": {"limit": 10, "window": 600},
    "me_deletion": {"limit": 10, "window": 600},
    # Catalogue et zones, publics et cacheables (spec 002) : large pour le CGNAT.
    "catalog_read": {"limit": 600, "window": 60},
}
# Listes de référence bornées sans pagination (spec 002) : quelques dizaines de lignes en V1.
REFERENCE_LIST_MAX = 200
# Quotas par Ops (décision de Zay, revue sécurité tâche 15, I2) : contre l'aspiration de la
# base par un Ops malveillant ou un compte compromis. Alerte à 50 %, refus au-delà.
OPS_QUOTAS = {
    "search": [(60, 3600), (300, 86400)],
    "reveal_phone": [(20, 3600), (60, 86400)],
    # Changement de numéro : demandes et approbations (revue sécurité tâche 16, I4).
    "phone_change": [(5, 3600), (15, 86400)],
}
OTP_PHONE_BLOCK_MAX_HOURS = 24
SMS_DAILY_CAP = env.int("SMS_DAILY_CAP", default=5000)
SMS_DAILY_CAP_BY_REGION = {"SN": env.int("SMS_DAILY_CAP_SN", default=5000)}
SMS_PREFIX_HOURLY_CAP = env.int("SMS_PREFIX_HOURLY_CAP", default=600)
SMS_BLOCK_HOURLY_CAP = env.int("SMS_BLOCK_HOURLY_CAP", default=30)
SMS_CONVERSION_MIN_RATE = 0.2
SMS_CONVERSION_MIN_VOLUME = 50

# --- Sessions (ADR 0007, spec 001 « Sessions et jetons ») : durées en secondes -------------
_DAY = 86400
SESSION_POLICIES = {
    "client": {"access": 900, "idle": 60 * _DAY, "absolute": 180 * _DAY},
    "pro": {"access": 900, "idle": 60 * _DAY, "absolute": 180 * _DAY},
    "web": {"access": 900, "idle": 30 * _DAY, "absolute": 90 * _DAY},
    "console": {"access": 900, "idle": 30 * _DAY, "absolute": 90 * _DAY},
    "console_ops": {"access": 600, "idle": 1800, "absolute": 12 * 3600},
}
MAX_ACTIVE_SESSIONS = 10
REFRESH_GRACE_SECONDS = _DAY  # Q15 : 24 h, une seule fois par rotation
DORMANT_AFTER_DAYS = 60  # Q17

# --- OTP (spec 001, « OTP ») ---------------------------------------------------------------
OTP_ALLOWED_REGIONS = env.list("OTP_ALLOWED_REGIONS", default=["SN"])  # Q1 : Sénégal seul en V1
TERMS_VERSION = env("TERMS_VERSION", default="2026-09-30")
# Défi client (S13, tâche 10) : livré éteint ; activable sans déploiement.
OTP_CHALLENGE_REQUIRED = env.bool("OTP_CHALLENGE_REQUIRED", default=False)
OTP_CHALLENGE_VERIFIER = env("OTP_CHALLENGE_VERIFIER", default="")
# Hachage SMS Retriever par app et par clé de signature (obligatoire en production).
SMS_ANDROID_APP_HASH = {
    "client": env("SMS_ANDROID_APP_HASH_CLIENT", default=""),
    "pro": env("SMS_ANDROID_APP_HASH_PRO", default=""),
}
WEBOTP_DOMAIN = env("WEBOTP_DOMAIN", default="jeflink.sn")
# Compte de revue des stores (S17) : numéros de SIM détenues par Jeflink, et fin de fenêtre
# (ISO 8601). Vide = aucune revue en cours. 45 jours au plus en production (check au démarrage).
OTP_REVIEW_ACCOUNTS = env.list("OTP_REVIEW_ACCOUNTS", default=[])
OTP_REVIEW_ENABLED_UNTIL = env("OTP_REVIEW_ENABLED_UNTIL", default="")
OTP_REVIEW_MAX_DAYS = 45

# --- Admin Django (tâche 21) : sessions courtes, second facteur revalidé ------------------
# Seul l'admin utilise des sessions Django (l'API est en Bearer JWT).
SESSION_COOKIE_AGE = 12 * 3600
ADMIN_MFA_MAX_AGE = 12 * 3600

# --- Invitations (spec 001, S19) ------------------------------------------------------------
INVITATION_TTL_DAYS = 7
INVITATIONS_PER_INVITER_DAILY = 20
# SMS d'invitation par numéro invité et par jour, tous pros confondus : un pro ne peut pas
# épuiser le budget SMS de connexion d'un numéro (5/h, 8/24 h) avec des invitations.
INVITATION_SMS_PER_PHONE_DAILY = 2
# SMS d'information (invitations…) : sous-budgets propres, et jamais au-delà de 50 % d'un
# plafond partagé, pour laisser la marge aux connexions (revue sécurité tâche 12, I3).
SMS_NOTICE_DAILY_CAP = env.int("SMS_NOTICE_DAILY_CAP", default=SMS_DAILY_CAP // 10)
SMS_NOTICE_PREFIX_HOURLY_CAP = 30
SMS_NOTICE_BLOCK_HOURLY_CAP = 3
SMS_NOTICE_MAX_SHARED_USE = 0.5
# Lien de téléchargement de l'app Pro, cité dans le SMS d'invitation (domaine à confirmer).
PRO_APP_LINK = env("PRO_APP_LINK", default="https://jeflink.sn/pro")

# Schéma OpenAPI servi seulement en local/test ; `make openapi` le génère hors ligne (S24).
SERVE_API_SCHEMA = DJANGO_ENV in {"local", "test"}

CELERY_BROKER_URL = REDIS_URL
# Celery garde la configuration LOGGING (et son filtre de données personnelles) : voir celery.py.
CELERY_WORKER_HIJACK_ROOT_LOGGER = False
CELERY_TASK_ACKS_LATE = True
CELERY_TASK_REJECT_ON_WORKER_LOST = True
# Au-delà de la durée maximale d'une tâche : pas de relivraison d'une tâche encore en cours.
CELERY_BROKER_TRANSPORT_OPTIONS = {"visibility_timeout": 3600}
CELERY_TIMEZONE = "UTC"
# Planification statique (spec 001, « Tâches Celery ») : pas de planificateur en base.
CELERY_BEAT_SCHEDULE = {
    "accounts-purge-auth-data": {
        "task": "jeflink.accounts.tasks.purge_auth_data",
        "schedule": 24 * 3600,
        "options": {"expires": 6 * 3600},
    },
    # Demande, devis, réservation (spec 003) : idempotentes. Expiration toutes les 5 minutes.
    "requests-expire-due": {
        "task": "jeflink.requests.tasks.expire_due",
        "schedule": 300,
        "options": {"expires": 240},
    },
    "bookings-cancel-unconfirmed": {
        "task": "jeflink.bookings.tasks.cancel_unconfirmed",
        "schedule": 300,
        "options": {"expires": 240},
    },
    # Clôture à la fin de la fenêtre de contestation, et rappel 12 h avant (spec 004).
    "bookings-close-due": {
        "task": "jeflink.bookings.tasks.close_due",
        "schedule": 300,
        "options": {"expires": 240},
    },
    "bookings-remind-disputes": {
        "task": "jeflink.bookings.tasks.remind_disputes",
        "schedule": 300,
        "options": {"expires": 240},
    },
    "requests-purge-locations": {
        "task": "jeflink.requests.tasks.purge_locations",
        "schedule": 24 * 3600,
        "options": {"expires": 6 * 3600},
    },
}

# Rétention des données d'authentification, en jours (spec 001 ; à valider par le consultant
# juridique avec la déclaration CDP, Q8). AuditEvent (5 ans) relève d'un archivage dédié.
AUTH_RETENTION = {
    "otp": 7,  # OtpChallenge, OtpDelivery, NoticeSms
    "mfa": 7,  # MfaChallenge, OpsEnrollmentToken expirés
    "closed_requests": 30,  # RoleInvitation et PhoneChangeRequest clos
    "sessions": 90,  # DeviceSession révoquées ou expirées (et leurs refresh retirés)
}

# --- Demande, devis, réservation (spec 003) : toutes les durées et limites sont des réglages ---
REQUEST_MAX_OPEN_PER_CLIENT = 3
REQUEST_CREATE_DAILY_LIMIT = 10  # créations par utilisateur et par 24 h (fermé si Redis tombe)
REQUEST_TTL = timedelta(hours=72)  # après le passage en « open » ; « needs_zone » ne compte pas
REQUEST_TTL_URGENT = timedelta(hours=24)
REQUEST_PREFERRED_MAX_DAYS = 30  # « un jour » souhaité : dans les 30 jours
# Repère et position d'une demande close sans réservation, vidés après (purge quotidienne).
REQUEST_LOCATION_RETENTION_DAYS = 30
QUOTE_MAX_ACTIVE = 3  # devis actifs par demande (pas de course au moins-disant)
PRO_MAX_SUBMITTED_QUOTES = 10  # devis « submitted » en même temps, par pro
QUOTE_TTL = timedelta(hours=48)
QUOTE_TTL_URGENT = timedelta(hours=12)
QUOTE_MAX_XOF = 5_000_000
QUOTE_VISIT_MAX_XOF = 15_000  # « Visite seulement » : plafond du déplacement
QUOTE_MAX_LINES = 8
BOOKING_CONFIRM_TTL = timedelta(hours=4)  # délai du pro pour confirmer
BOOKING_CONFIRM_TTL_URGENT = timedelta(hours=1)
# Le délai ne court pas de 21 h à 7 h, heure de Dakar : (début, fin) en heures.
BOOKING_CONFIRM_QUIET_HOURS = (21, 7)
BOOKING_LATE_CANCEL_WINDOW = timedelta(hours=2)  # annulation « tardive » avant le créneau
# Déroulé de l'intervention, clôture et litige (spec 004).
BOOKING_DISPUTE_WINDOW = timedelta(hours=48)  # contestation possible après « terminé »
BOOKING_DISPUTE_REMINDER = timedelta(hours=12)  # rappel au client avant la fin de la fenêtre
# Heure de l'appareil acceptée pour une action rejouée plus tard (file hors ligne, étape 6).
OCCURRED_AT_MAX_SKEW = timedelta(hours=24)
# Plages de la journée (heure de Dakar) : (début, fin) en heures, pour les créneaux des devis.
SLOT_PERIODS = {"morning": (8, 12), "afternoon": (12, 17), "evening": (17, 21)}

# --- Stockage d'objets (ADR 0011) : bucket privé, URL signées courtes --------------------------
# S3_ENDPOINT : hôte vu par l'API (réseau Docker) ; S3_PUBLIC_ENDPOINT : hôte vu par le
# navigateur, celui pour lequel les URL sont signées. Identifiants factices en local.
S3_ENDPOINT = env("S3_ENDPOINT", default="")
S3_PUBLIC_ENDPOINT = env("S3_PUBLIC_ENDPOINT", default="")
S3_BUCKET = env("S3_BUCKET", default="")
S3_ACCESS_KEY = env("S3_ACCESS_KEY", default="")
S3_SECRET_KEY = env("S3_SECRET_KEY", default="")
S3_REGION = env("S3_REGION", default="us-east-1")
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    "photos": {
        "BACKEND": "storages.backends.s3.S3Storage",
        "OPTIONS": {
            "bucket_name": S3_BUCKET,
            "endpoint_url": S3_ENDPOINT or None,
            "access_key": S3_ACCESS_KEY or None,
            "secret_key": S3_SECRET_KEY or None,
            "region_name": S3_REGION,
            "signature_version": "s3v4",
            "addressing_style": "path",
            "default_acl": None,
            "querystring_auth": True,
            "file_overwrite": True,
        },
    },
}
# Taille décodée maximale d'une image envoyée (anti « bombe de décompression »).
IMAGE_MAX_PIXELS = 40_000_000
BOOKING_PHOTO_URL_TTL = 600  # secondes : validité d'une URL signée de photo

# IA (côté serveur uniquement, règle 4) : modèles jamais en dur dans le code.
AI_MODEL_DEFAULT = env("AI_MODEL_DEFAULT", default="")
AI_MODEL_FAST = env("AI_MODEL_FAST", default="")

# Notifications métier (spec 003) : « log » (local, test) ou « none » ; push et SMS à l'étape 6.
# Vide : « log » en local/test, « none » ailleurs.
NOTIFICATIONS_ADAPTER = env("NOTIFICATIONS_ADAPTER", default="")

# SMS (ADR 0008) : adaptateur obligatoire hors local/test ; « fake » y est interdit (S23).
SMS_GATEWAY = env("SMS_GATEWAY", default="")
SMS_SENDER_ID = env("SMS_SENDER_ID", default="JEFLINK")

# Paiements : cash | manual_mobile_money | wiipay | fake (règle 3).
PAYMENT_GATEWAY = env("PAYMENT_GATEWAY", default="manual_mobile_money")
