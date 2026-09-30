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
    is_staff = models.BooleanField(default=False)
    is_review_account = models.BooleanField(default=False)
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
