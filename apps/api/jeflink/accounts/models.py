from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.db import models
from django.db.models import Q

from jeflink.common.models import BaseModel

from .phone import normalize_phone

E164_REGEX = r"^\+[1-9][0-9]{7,14}$"


class UserManager(BaseUserManager["User"]):
    use_in_migrations = True

    def create_user(self, phone: str, **extra) -> "User":
        user = self.model(phone=normalize_phone(phone), **extra)
        user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_superuser(self, phone: str, password: str, **extra) -> "User":
        """Compte technique (admin Django interne). Jamais de session API (S3)."""
        user = self.model(phone=normalize_phone(phone), is_staff=True, is_superuser=True, **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user


class User(BaseModel, AbstractBaseUser, PermissionsMixin):
    """Compte Jeflink. Le rôle client est implicite ; les autres sont des ``RoleGrant``."""

    class Language(models.TextChoices):
        FR = "fr", "Français"
        WO = "wo", "Wolof"

    class ProfileStatus(models.TextChoices):
        GUEST = "guest", "Invité"
        COMPLETE = "complete", "Complet"

    class DeactivationReason(models.TextChoices):
        FRAUD = "fraud", "Fraude"
        USER_REQUEST = "user_request", "Demande de l'utilisateur"
        OPS_OTHER = "ops_other", "Autre (Ops)"

    phone = models.CharField(max_length=16, unique=True, null=True, blank=True)
    phone_verified_at = models.DateTimeField(null=True, blank=True)
    phone_changed_at = models.DateTimeField(null=True, blank=True)
    display_name = models.CharField(max_length=80, blank=True)
    email = models.EmailField(blank=True)
    preferred_language = models.CharField(
        max_length=2, choices=Language.choices, default=Language.FR
    )
    profile_status = models.CharField(
        max_length=8, choices=ProfileStatus.choices, default=ProfileStatus.GUEST
    )
    terms_version = models.CharField(max_length=16, blank=True)
    terms_accepted_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    deactivation_reason = models.CharField(
        max_length=16, choices=DeactivationReason.choices, blank=True
    )
    # Auteur de la désactivation : S30 exige qu'un autre Ops réactive un compte « fraud ».
    deactivated_by = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    is_staff = models.BooleanField(default=False)
    is_review_account = models.BooleanField(default=False)
    # Compte dormant (S18) : posé à la première connexion restreinte, levé seulement par l'Ops
    # ou par « Repartir de zéro ». Tant qu'il est posé, toute nouvelle session est restreinte.
    dormant_restricted_since = models.DateTimeField(null=True, blank=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    objects = UserManager()

    USERNAME_FIELD = "phone"
    REQUIRED_FIELDS: list[str] = []

    class Meta:
        permissions = [
            ("ops_accounts_view", "Ops : consulter les comptes"),
            ("ops_accounts_manage", "Ops : gérer les comptes (sessions, blocages, état)"),
            ("ops_accounts_change_phone", "Ops : changer le numéro d'un compte"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(phone__isnull=True) | Q(phone__regex=E164_REGEX),
                name="user_phone_e164",
            ),
            models.CheckConstraint(
                condition=Q(phone__isnull=False) | Q(deleted_at__isnull=False),
                name="user_phone_required_unless_deleted",
            ),
            models.CheckConstraint(
                condition=~Q(profile_status="complete") | ~Q(display_name=""),
                name="user_complete_requires_display_name",
            ),
            models.CheckConstraint(
                condition=Q(is_active=True)
                | ~Q(deactivation_reason="")
                | Q(deleted_at__isnull=False),
                name="user_inactive_has_reason",
            ),
        ]

    def __str__(self) -> str:
        return str(self.public_id)

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None


class Role(models.TextChoices):
    OWNER = "owner", "Prestataire (gérant)"
    TECHNICIAN = "technician", "Technicien"
    OPS = "ops", "Équipe Jeflink"


class RoleGrant(BaseModel):
    """Rôle accordé. Historique conservé : un retrait renseigne ``revoked_at``."""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="role_grants")
    role = models.CharField(max_length=16, choices=Role.choices)
    granted_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    reason_code = models.CharField(max_length=32)
    revoked_at = models.DateTimeField(null=True, blank=True)
    revoked_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "role"],
                condition=Q(revoked_at__isnull=True),
                name="rolegrant_one_active_per_role",
            ),
        ]


class OtpPhoneBlock(models.Model):
    """Blocage progressif des nouveaux challenges d'un numéro après trop d'échecs (S8).

    Le numéro n'est jamais stocké : seul son HMAC. Les sessions existantes ne sont pas touchées.
    """

    phone_hmac = models.CharField(max_length=64, unique=True)
    level = models.PositiveSmallIntegerField(default=0)
    blocked_until = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"blocage niveau {self.level}"


class DeviceSession(BaseModel):
    """Une session par appareil (ADR 0007). Son ``public_id`` est le claim ``sid`` du JWT.

    Le refresh n'est jamais stocké en clair : seul son SHA-256.
    """

    class App(models.TextChoices):
        CLIENT = "client", "App client"
        PRO = "pro", "App Pro"
        WEB = "web", "Web"
        CONSOLE = "console", "Console"

    class Platform(models.TextChoices):
        ANDROID = "android", "Android"
        IOS = "ios", "iOS"
        WEB = "web", "Web"

    class RevokedReason(models.TextChoices):
        LOGOUT = "logout", "Déconnexion"
        USER_REVOKED = "user_revoked", "Révoquée par l'utilisateur"
        OPS_REVOKED = "ops_revoked", "Révoquée par l'Ops"
        REUSE_DETECTED = "reuse_detected", "Réutilisation de refresh"
        LIMIT = "limit", "Trop de sessions"
        REPLACED = "replaced", "Remplacée sur le même appareil"
        PHONE_CHANGED = "phone_changed", "Numéro changé"
        ACCOUNT_DELETED = "account_deleted", "Compte supprimé"
        ACCOUNT_DISABLED = "account_disabled", "Compte désactivé"
        OPS_ROLE_CHANGED = "ops_role_changed", "Rôle ops modifié"

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="device_sessions")
    app = models.CharField(max_length=8, choices=App.choices)
    # Politique de durée figée à la création (client, pro, web, console, console_ops).
    policy = models.CharField(max_length=12)
    platform = models.CharField(max_length=8, choices=Platform.choices)
    device_label = models.CharField(max_length=60, blank=True)
    install_id = models.CharField(max_length=64, blank=True)
    refresh_hash = models.CharField(max_length=64, unique=True)
    previous_refresh_hash = models.CharField(max_length=64, blank=True, db_index=True)
    rotated_at = models.DateTimeField(null=True, blank=True)
    grace_used_at = models.DateTimeField(null=True, blank=True)
    auth_time = models.DateTimeField()
    mfa_verified_at = models.DateTimeField(null=True, blank=True)
    # Compte dormant (S18) : aucune donnée personnelle tant que la restriction n'est pas levée.
    restricted = models.BooleanField(default=False)
    last_seen_at = models.DateTimeField()
    idle_expires_at = models.DateTimeField()
    absolute_expires_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True, blank=True)
    revoked_reason = models.CharField(max_length=20, choices=RevokedReason.choices, blank=True)

    class Meta:
        indexes = [models.Index(fields=["user", "revoked_at"])]
        constraints = [
            models.CheckConstraint(
                condition=Q(revoked_at__isnull=True) | ~Q(revoked_reason=""),
                name="devicesession_revoked_has_reason",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.app} · {self.platform}"


class RetiredRefreshToken(models.Model):
    """Refresh déjà remplacés : les présenter à nouveau révèle une réutilisation (ADR 0007)."""

    session = models.ForeignKey(DeviceSession, on_delete=models.CASCADE, related_name="+")
    refresh_hash = models.CharField(max_length=64, unique=True)
    retired_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"refresh retiré · {self.retired_at:%Y-%m-%d}"


class OtpChallenge(BaseModel):
    """Un parcours de vérification par code (spec 001, OTP). Ni code ni secret en clair."""

    class Purpose(models.TextChoices):
        LOGIN = "login", "Connexion"
        DELETE_ACCOUNT = "delete_account", "Suppression du compte"
        CHANGE_PHONE = "change_phone", "Changement de numéro"
        SENSITIVE_ACTION = "sensitive_action", "Action sensible"

    class Status(models.TextChoices):
        PENDING = "pending", "En attente"
        VERIFIED = "verified", "Vérifié"
        LOCKED = "locked", "Verrouillé"
        EXPIRED = "expired", "Expiré"

    phone = models.CharField(max_length=16)
    region = models.CharField(max_length=2)
    purpose = models.CharField(max_length=16, choices=Purpose.choices)
    user = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.CASCADE, related_name="+"
    )
    challenge_secret_hash = models.CharField(max_length=64)
    app = models.CharField(max_length=8, choices=DeviceSession.App.choices)
    language = models.CharField(max_length=2, default="fr")
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.PENDING)
    failed_attempts = models.PositiveSmallIntegerField(default=0)
    expires_at = models.DateTimeField()
    verified_at = models.DateTimeField(null=True, blank=True)
    verified_install_id = models.CharField(max_length=64, blank=True)
    session = models.ForeignKey(
        DeviceSession, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        indexes = [models.Index(fields=["phone", "created_at"])]
        constraints = [
            models.CheckConstraint(
                condition=Q(failed_attempts__lte=5), name="otpchallenge_max_attempts"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.purpose} · {self.status}"


class OtpDelivery(BaseModel):
    """Un envoi de code (3 au plus par challenge). Le code n'existe qu'en HMAC."""

    class Channel(models.TextChoices):
        SMS = "sms", "SMS"
        WHATSAPP = "whatsapp", "WhatsApp"
        VOICE = "voice", "Appel vocal"

    class Status(models.TextChoices):
        QUEUED = "queued", "En file"
        SENT = "sent", "Envoyé"
        FAILED = "failed", "Échec"
        UNKNOWN = "unknown", "Issue inconnue"

    challenge = models.ForeignKey(OtpChallenge, on_delete=models.CASCADE, related_name="deliveries")
    attempt_no = models.PositiveSmallIntegerField()
    channel = models.CharField(max_length=8, choices=Channel.choices, default=Channel.SMS)
    code_hash = models.CharField(max_length=64, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.QUEUED)
    gateway = models.CharField(max_length=32, blank=True)
    provider_message_id = models.CharField(max_length=128, blank=True)
    segments = models.PositiveSmallIntegerField(default=0)
    error_code = models.CharField(max_length=64, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["challenge", "attempt_no"], name="otpdelivery_unique_attempt"
            ),
            models.CheckConstraint(
                condition=Q(attempt_no__gte=1) & Q(attempt_no__lte=3),
                name="otpdelivery_attempt_range",
            ),
        ]

    def __str__(self) -> str:
        return f"envoi {self.attempt_no} · {self.status}"
