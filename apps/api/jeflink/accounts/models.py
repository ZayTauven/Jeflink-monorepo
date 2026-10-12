import re

from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models
from django.db.models import Avg, Count

PHONE_E164_SN = RegexValidator(
    r"^\+221\d{9}$", "Numéro sénégalais attendu : +221 suivi de 9 chiffres."
)


def normalize_phone(raw: str) -> str:
    """« 77 123 45 67 », « 0022177… » ou « +221 77… » → « +221771234567 ». Vide reste vide."""
    digits = re.sub(r"\D", "", raw or "")
    if not digits:
        return ""
    if digits.startswith("00221"):
        digits = digits[5:]
    elif digits.startswith("221") and len(digits) == 12:
        digits = digits[3:]
    value = f"+221{digits}"
    PHONE_E164_SN(value)
    return value


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, email, password, **extra):
        if not email:
            raise ValueError("L'email est obligatoire.")
        user = self.model(email=self.normalize_email(email).lower(), **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra):
        extra.setdefault("is_staff", False)
        extra.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra)

    def create_superuser(self, email, password=None, **extra):
        extra.update(is_staff=True, is_superuser=True)
        return self._create_user(email, password, **extra)


class User(AbstractUser):
    """Compte Jeflink : connexion par email + mot de passe (OTP téléphone prévu sur mobile)."""

    class Role(models.TextChoices):
        CLIENT = "client", "Client"
        PRO = "pro", "Pro"

    username = None
    email = models.EmailField("email", unique=True)
    phone = models.CharField("téléphone", max_length=13, blank=True, validators=[PHONE_E164_SN])
    role = models.CharField("rôle", max_length=10, choices=Role.choices, default=Role.CLIENT)
    photo = models.CharField(
        "photo", max_length=200, blank=True, help_text="Chemin d'image servi par le site web."
    )

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects = UserManager()

    class Meta:
        verbose_name = "compte"

    def __str__(self):
        return self.get_full_name() or self.email

    @property
    def is_pro(self) -> bool:
        return self.role == self.Role.PRO

    @property
    def public_name(self) -> str:
        """Prénom + initiale : ce qu'on montre aux autres utilisateurs."""
        initial = f" {self.last_name[:1]}." if self.last_name else ""
        return f"{self.first_name}{initial}".strip() or "Utilisateur"


class ProProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="pro_profile")
    headline = models.CharField("accroche", max_length=120, blank=True)
    bio = models.TextField("présentation", blank=True)
    trades = models.ManyToManyField("catalog.Trade", related_name="pros", verbose_name="métiers")
    zones = models.ManyToManyField(
        "catalog.Zone", related_name="pros", blank=True, verbose_name="quartiers desservis"
    )
    years_experience = models.PositiveSmallIntegerField("années d'expérience", default=0)
    is_verified = models.BooleanField(
        "vérifié",
        default=False,
        help_text="Seuls les pros vérifiés par l'équipe Jeflink peuvent envoyer des devis.",
    )
    photo = models.CharField(
        "photo", max_length=200, blank=True, help_text="Chemin d'image servi par le site web."
    )

    class Meta:
        verbose_name = "profil pro"
        verbose_name_plural = "profils pros"

    def __str__(self):
        return str(self.user)

    def clean(self):
        if self.user_id and not self.user.is_pro:
            raise ValidationError("Ce compte n'a pas le rôle « Pro ».")

    def rating(self) -> dict:
        from jeflink.jobs.models import Review

        agg = Review.objects.filter(request__pro=self.user).aggregate(
            avg=Avg("rating"), n=Count("id")
        )
        return {"average": round(agg["avg"], 1) if agg["avg"] else None, "count": agg["n"]}


class ContactMessage(models.Model):
    """Message envoyé depuis la page Contact du site, lu par l'équipe dans l'admin."""

    name = models.CharField("nom", max_length=120)
    email = models.EmailField()
    message = models.TextField()
    is_handled = models.BooleanField("traité", default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "message de contact"
        verbose_name_plural = "messages de contact"

    def __str__(self):
        return f"{self.name} — {self.created_at:%d/%m/%Y}"
