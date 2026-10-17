import re

from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models
from django.db.models import Avg, Count, F

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

    class StaffRole(models.TextChoices):
        """Rôle d'un membre de l'équipe dans la console (comptes is_staff)."""

        SUPER = "super", "Super admin"
        OPS = "ops", "Opérations"
        MARKETING = "marketing", "Marketing"
        FINANCE = "finance", "Finance"

    class ContactPref(models.TextChoices):
        """Comment l'autre partie le joint une fois la mission réservée."""

        ANY = "", "Appel ou WhatsApp"
        CALL = "call", "Appel"
        WHATSAPP = "whatsapp", "WhatsApp"

    class ContactHours(models.TextChoices):
        ANY = "", "Toute la journée"
        MORNING = "morning", "Le matin (8 h – 12 h)"
        AFTERNOON = "afternoon", "L'après-midi (12 h – 17 h)"
        EVENING = "evening", "Le soir (17 h – 21 h)"

    username = None
    email = models.EmailField("email", unique=True)
    phone = models.CharField("téléphone", max_length=13, blank=True, validators=[PHONE_E164_SN])
    role = models.CharField("rôle", max_length=10, choices=Role.choices, default=Role.CLIENT)
    photo = models.CharField(
        "photo", max_length=200, blank=True, help_text="Chemin d'image servi par le site web."
    )
    contact_pref = models.CharField(
        "joignable par", max_length=10, choices=ContactPref.choices, blank=True, default=""
    )
    contact_hours = models.CharField(
        "joignable", max_length=10, choices=ContactHours.choices, blank=True, default=""
    )
    staff_role = models.CharField(
        "rôle dans l'équipe",
        max_length=12,
        choices=StaffRole.choices,
        blank=True,
        help_text="Pour les comptes de l'équipe : ce qu'ils voient et font dans la console.",
    )
    suspension_reason = models.CharField(
        "motif de suspension",
        max_length=200,
        blank=True,
        help_text="Renseigné quand l'équipe suspend le compte (is_active = faux).",
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
    def console_role(self) -> str:
        """Rôle effectif dans la console : super admin pour un superuser, sinon le rôle choisi
        (Opérations par défaut). Vide pour un compte hors équipe."""
        if not self.is_staff:
            return ""
        if self.is_superuser:
            return self.StaffRole.SUPER
        return self.staff_role or self.StaffRole.OPS

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
    # Ajoutés par le pro depuis son profil : il ne voit ni ne chiffre ces demandes tant que
    # l'équipe ne les a pas validés (console, fiche pro).
    pending_trades = models.ManyToManyField(
        "catalog.Trade", related_name="+", blank=True, verbose_name="métiers demandés"
    )
    trade_note = models.CharField(
        "message sur les métiers",
        max_length=300,
        blank=True,
        help_text="Dernier refus d'un métier demandé ; affiché au pro dans son profil.",
    )
    zones = models.ManyToManyField(
        "catalog.Zone", related_name="pros", blank=True, verbose_name="quartiers desservis"
    )
    years_experience = models.PositiveSmallIntegerField("années d'expérience", default=0)
    is_verified = models.BooleanField(
        "vérifié",
        default=False,
        help_text="Seuls les pros vérifiés par l'équipe Jeflink peuvent envoyer des devis.",
    )
    verified_at = models.DateTimeField("vérifié le", null=True, blank=True)
    verification_note = models.CharField(
        "motif du refus",
        max_length=300,
        blank=True,
        help_text="Ce qui manque pour être vérifié ; affiché au pro dans son espace.",
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

        agg = Review.objects.filter(request__pro=self.user, is_hidden=False).aggregate(
            avg=Avg("rating"), n=Count("id")
        )
        return {"average": round(agg["avg"], 1) if agg["avg"] else None, "count": agg["n"]}

    # Badge « Pro confirmé » : gagné seul, par le travail fait sur Jeflink.
    CONFIRMED_MISSIONS = 10
    CONFIRMED_RATING = 4.5

    def is_confirmed(self) -> bool:
        """Vérifié, 10 missions terminées, note moyenne d'au moins 4,5 et aucun litige perdu
        (résolu en faveur du client qui l'avait ouvert)."""
        from jeflink.jobs.models import Dispute, ServiceRequest

        if not self.is_verified or not self.user.is_active:
            return False
        done = self.user.missions.filter(status=ServiceRequest.Status.DONE).count()
        if done < self.CONFIRMED_MISSIONS:
            return False
        average = self.rating()["average"]
        if average is None or average < self.CONFIRMED_RATING:
            return False
        lost = Dispute.objects.filter(
            request__pro=self.user,
            status=Dispute.Status.RESOLVED,
            opened_by=F("request__client"),
        )
        return not lost.exists()

    def has_accepted_id(self) -> bool:
        return self.documents.filter(
            kind=ProDocument.Kind.ID, status=ProDocument.Status.ACCEPTED
        ).exists()


class ProDocument(models.Model):
    """Justificatif envoyé par un pro, examiné par l'équipe. Privé : fichier hors de /media/,
    lu seulement par le pro et l'équipe Opérations. Une pièce d'identité acceptée est exigée
    pour vérifier le pro."""

    MAX = 10

    class Kind(models.TextChoices):
        ID = "id", "Pièce d'identité"
        CERTIFICATE = "certificate", "Diplôme ou attestation"
        OTHER = "other", "Autre justificatif"

    class Status(models.TextChoices):
        PENDING = "pending", "À examiner"
        ACCEPTED = "accepted", "Accepté"
        REJECTED = "rejected", "Refusé"

    profile = models.ForeignKey(ProProfile, on_delete=models.CASCADE, related_name="documents")
    kind = models.CharField("type", max_length=12, choices=Kind.choices)
    file = models.CharField("fichier", max_length=120, help_text="Chemin dans PRIVATE_ROOT.")
    content_type = models.CharField(max_length=40)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    note = models.CharField(
        "motif du refus", max_length=300, blank=True, help_text="Affiché au pro dans son profil."
    )
    reviewed_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        verbose_name = "document d'un pro"
        verbose_name_plural = "documents des pros"

    def __str__(self):
        return f"{self.get_kind_display()} — {self.profile}"


class SavedAddress(models.Model):
    """Adresse enregistrée par un client (quartier + repère), reprise dans ses demandes.

    Pas de rue ni de numéro : à Dakar on se repère (« derrière la pharmacie, portail bleu »).
    """

    MAX = 5

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="addresses")
    label = models.CharField("nom", max_length=40, help_text="Maison, Bureau, Chez maman…")
    zone = models.ForeignKey("catalog.Zone", on_delete=models.PROTECT, verbose_name="quartier")
    landmark = models.CharField("repère", max_length=160, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]
        verbose_name = "adresse enregistrée"
        verbose_name_plural = "adresses enregistrées"

    def __str__(self):
        return f"{self.label} — {self.zone}"


def save_address(user, label: str, zone, landmark: str) -> SavedAddress | None:
    """Enregistre l'adresse d'une demande dans « Mes adresses », sauf doublon ou liste pleine
    (la demande est publiée de toute façon : rien ne bloque le client)."""
    mine = user.addresses
    if mine.count() >= SavedAddress.MAX or mine.filter(zone=zone, landmark=landmark).exists():
        return None
    return SavedAddress.objects.create(user=user, label=label[:40], zone=zone, landmark=landmark)


class ContactMessage(models.Model):
    """Message envoyé depuis la page Contact du site, lu par l'équipe dans l'admin."""

    name = models.CharField("nom", max_length=120)
    email = models.EmailField()
    message = models.TextField()
    is_handled = models.BooleanField("traité", default=False)
    handled_at = models.DateTimeField("traité le", null=True, blank=True)
    handled_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "message de contact"
        verbose_name_plural = "messages de contact"

    def __str__(self):
        return f"{self.name} — {self.created_at:%d/%m/%Y}"
