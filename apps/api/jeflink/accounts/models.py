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
            ("ops_accounts_reveal_phone", "Ops : afficher le numéro complet d'un compte"),
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
        MFA_LOCKED = "mfa_locked", "Second facteur verrouillé"
        MFA_RESET = "mfa_reset", "Second facteur réinitialisé"

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
        SENDING = "sending", "Envoi en cours"
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
        # created_at : comptages de repli en base (db_counts) et purge.
        indexes = [models.Index(fields=["created_at"])]
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


class RoleInvitation(BaseModel):
    """Invitation à un rôle pro, en attente de l'acceptation explicite du titulaire du numéro (S19).

    Aucun ``User`` ni ``RoleGrant`` n'existe avant l'acceptation. Le numéro n'est gardé que tant
    que l'invitation est en attente : il est effacé à sa clôture (acceptée, refusée, expirée).
    """

    class Status(models.TextChoices):
        PENDING = "pending", "En attente"
        ACCEPTED = "accepted", "Acceptée"
        DECLINED = "declined", "Refusée"
        EXPIRED = "expired", "Expirée"

    phone = models.CharField(max_length=16, blank=True)
    # Pseudonyme gardé après la clôture : refus idempotent, pause des SMS après un refus.
    phone_hmac = models.CharField(max_length=64)
    role = models.CharField(max_length=16, choices=Role.choices)
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.PENDING)
    invited_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name="+")
    display_name_hint = models.CharField(max_length=80, blank=True)
    # Référence opaque appartenant à providers (équipe) ; accounts ne l'interprète jamais.
    context_ref = models.UUIDField()
    expires_at = models.DateTimeField()
    accepted_at = models.DateTimeField(null=True, blank=True)
    accepted_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    declined_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["phone", "status"]),
            # Quota quotidien par pro (compté en base, tient sans Redis).
            models.Index(fields=["invited_by", "created_at"]),
            models.Index(fields=["invited_by", "phone_hmac"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["phone", "role", "context_ref"],
                condition=Q(status="pending"),
                name="roleinvitation_one_pending",
            ),
            models.CheckConstraint(
                condition=Q(role__in=["owner", "technician"]), name="roleinvitation_pro_role"
            ),
            models.CheckConstraint(
                condition=(Q(status="pending") & Q(phone__regex=E164_REGEX))
                | (~Q(status="pending") & Q(phone="")),
                name="roleinvitation_phone_only_while_pending",
            ),
        ]

    def __str__(self) -> str:
        return f"invitation {self.role} · {self.status}"


class NoticeSms(BaseModel):
    """SMS d'information sans code (invitation, information à l'ancien numéro).

    État d'envoi idempotent comme ``OtpDelivery``. Le numéro en clair n'est gardé que jusqu'à
    l'issue de l'envoi ; son HMAC reste pour le comptage de repli si Redis tombe (S8).
    """

    class Kind(models.TextChoices):
        INVITATION = "invitation", "Invitation"
        PHONE_CHANGED = "phone_changed", "Information à l'ancien numéro"
        PHONE_CHANGE_REQUESTED = "phone_change_req", "Alerte : changement de numéro demandé"

    class Status(models.TextChoices):
        QUEUED = "queued", "En file"
        SENDING = "sending", "Envoi en cours"
        SENT = "sent", "Envoyé"
        FAILED = "failed", "Échec"
        UNKNOWN = "unknown", "Issue inconnue"

    kind = models.CharField(max_length=16, choices=Kind.choices)
    phone = models.CharField(max_length=16, blank=True)
    phone_hmac = models.CharField(max_length=64)
    region = models.CharField(max_length=2)
    language = models.CharField(max_length=2, default="fr")
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.QUEUED)
    gateway = models.CharField(max_length=32, blank=True)
    provider_message_id = models.CharField(max_length=128, blank=True)
    segments = models.PositiveSmallIntegerField(default=0)
    error_code = models.CharField(max_length=64, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["created_at"]),
            models.Index(fields=["phone_hmac", "created_at"]),
        ]

    def __str__(self) -> str:
        return f"SMS {self.kind} · {self.status}"


class TotpDevice(BaseModel):
    """Second facteur TOTP d'un Ops (S1). Le secret n'existe qu'en MultiFernet."""

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="totp_device")
    secret_encrypted = models.TextField()
    confirmed_at = models.DateTimeField(null=True, blank=True)
    # Anti-rejeu : un code d'un pas de temps déjà utilisé (ou antérieur) est refusé.
    last_used_step = models.BigIntegerField(default=0)
    # Horodatages (epoch) des échecs des dernières 24 h : 10 → verrou jusqu'à reset_ops_mfa.
    # Fenêtre glissante, comptée en base sous verrou de ligne (sans Redis). Au plus 10 entrées.
    recent_failures = models.JSONField(default=list, blank=True)
    locked_at = models.DateTimeField(null=True, blank=True)

    def __str__(self) -> str:
        return "TOTP confirmé" if self.confirmed_at else "TOTP en attente"


class OpsEnrollmentToken(BaseModel):
    """Jeton d'enrôlement TOTP remis hors bande (S1) : 24 h, usage unique, stocké haché."""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="+")
    token_hash = models.CharField(max_length=64, unique=True)
    issued_by_operator = models.CharField(max_length=64)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)

    def __str__(self) -> str:
        return f"jeton d'enrôlement · {self.expires_at:%Y-%m-%d %H:%M}"


class MfaChallenge(BaseModel):
    """Étape entre l'OTP et le TOTP d'un Ops sur la console (S1) : 5 min, 5 essais."""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="+")
    otp_challenge = models.ForeignKey(OtpChallenge, on_delete=models.CASCADE, related_name="+")
    token_hash = models.CharField(max_length=64, unique=True)
    app = models.CharField(max_length=8, choices=DeviceSession.App.choices)
    device_label = models.CharField(max_length=60, blank=True)
    install_id = models.CharField(max_length=64, blank=True)
    # Enrôlement en cours : jeton présenté à setup, consommé à confirm.
    enrollment_token = models.ForeignKey(
        OpsEnrollmentToken, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)
    failed_attempts = models.PositiveSmallIntegerField(default=0)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(failed_attempts__lte=5), name="mfachallenge_max_attempts"
            ),
            models.CheckConstraint(condition=Q(app="console"), name="mfachallenge_console_only"),
        ]

    def __str__(self) -> str:
        return "challenge MFA"


class PhoneChangeRequest(BaseModel):
    """Changement de numéro par l'Ops (S2) : jamais en libre-service.

    Compte ``owner`` ou ``technician`` : un second Ops approuve. Le code part vers le nouveau
    numéro et l'utilisateur le saisit lui-même ; l'Ops ne le voit jamais. Le nouveau numéro
    n'est gardé que tant que la demande est ouverte.
    """

    class Status(models.TextChoices):
        PENDING_APPROVAL = "pending_approval", "En attente d'approbation"
        APPROVED = "approved", "Approuvée, code envoyé"
        COMPLETED = "completed", "Terminée"
        REJECTED = "rejected", "Refusée"
        EXPIRED = "expired", "Expirée"

    OPEN = (Status.PENDING_APPROVAL, Status.APPROVED)

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="+")
    new_phone = models.CharField(max_length=16, blank=True)
    new_phone_hmac = models.CharField(max_length=64)
    requested_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name="+")
    approved_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    rejected_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    requires_approval = models.BooleanField()
    reason_code = models.CharField(max_length=32)
    note = models.CharField(max_length=280, blank=True)
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.PENDING_APPROVAL
    )
    # Dernier challenge change_phone envoyé (3 envois au plus par demande).
    challenge = models.ForeignKey(
        OtpChallenge, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    codes_sent = models.PositiveSmallIntegerField(default=0)
    expires_at = models.DateTimeField()
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(approved_by__isnull=True) | ~Q(approved_by=models.F("requested_by")),
                name="phonechange_second_operator",
            ),
            models.CheckConstraint(
                condition=(Q(status__in=["pending_approval", "approved"]) & ~Q(new_phone=""))
                | (~Q(status__in=["pending_approval", "approved"]) & Q(new_phone="")),
                name="phonechange_new_phone_only_while_open",
            ),
            models.CheckConstraint(condition=Q(codes_sent__lte=3), name="phonechange_max_codes"),
            models.UniqueConstraint(
                fields=["user"],
                condition=Q(status__in=["pending_approval", "approved"]),
                name="phonechange_one_open_per_user",
            ),
            models.UniqueConstraint(
                fields=["new_phone"],
                condition=Q(status__in=["pending_approval", "approved"]),
                name="phonechange_one_open_per_new_phone",
            ),
        ]

    def __str__(self) -> str:
        return f"changement de numéro · {self.status}"
