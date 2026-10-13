from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class ServiceRequest(models.Model):
    """Demande d'un client. Le statut ne change que par ``jobs.services.transition``."""

    class Status(models.TextChoices):
        OPEN = "open", "En attente de devis"
        BOOKED = "booked", "Pro réservé"
        # Le client a annulé une mission réservée : le support le rappelle, puis confirme
        # l'annulation ou maintient la mission. L'argent reste compté d'ici là.
        CANCELLING = "cancelling", "Annulation demandée"
        DONE = "done", "Terminée"
        CANCELLED = "cancelled", "Annulée"

    class CancelReason(models.TextChoices):
        SOLVED = "solved", "Le problème s'est réglé"
        OTHER_PRO = "other_pro", "J'ai trouvé quelqu'un d'autre"
        PRICE = "price", "Le prix ne me convient pas"
        DELAY = "delay", "Trop d'attente"
        PRO = "pro", "Un souci avec le pro"
        MISTAKE = "mistake", "Demande faite par erreur"
        OTHER = "other", "Autre"

    client = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="requests"
    )
    trade = models.ForeignKey("catalog.Trade", on_delete=models.PROTECT, verbose_name="métier")
    zone = models.ForeignKey("catalog.Zone", on_delete=models.PROTECT, verbose_name="quartier")
    title = models.CharField("titre", max_length=120)
    description = models.TextField()
    landmark = models.CharField("repère", max_length=160, blank=True)
    preferred_date = models.DateField("date souhaitée", null=True, blank=True)
    is_urgent = models.BooleanField("urgent", default=False)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.OPEN)
    pro = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="missions",
        help_text="Le pro dont le devis a été accepté.",
    )
    # Montants figés quand le client choisit un devis (F CFA entiers). Paiement sur place :
    # le client paie au pro price - discount ; le pro doit à Jeflink commission - discount.
    price = models.PositiveIntegerField("prix du devis accepté", null=True, blank=True)
    discount = models.PositiveIntegerField("remise Jeflink", default=0)
    coupon = models.ForeignKey(
        "Coupon",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="requests",
        verbose_name="code promo",
    )
    commission_rate = models.PositiveSmallIntegerField("taux de commission (%)", default=0)
    commission = models.PositiveIntegerField("commission Jeflink", default=0)
    staff_note = models.TextField(
        "note interne", blank=True, help_text="Visible de l'équipe Jeflink seulement."
    )
    # Motif donné par le client en annulant (dernière annulation demandée).
    cancel_reason = models.CharField(
        "motif d'annulation", max_length=12, choices=CancelReason.choices, blank=True
    )
    cancel_note = models.CharField("précision du client", max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "demande"

    def __str__(self):
        return f"#{self.pk} {self.title}"


class Quote(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "En attente"
        ACCEPTED = "accepted", "Accepté"
        DECLINED = "declined", "Non retenu"

    request = models.ForeignKey(ServiceRequest, on_delete=models.CASCADE, related_name="quotes")
    pro = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="quotes"
    )
    amount = models.PositiveIntegerField("montant (F CFA)")
    message = models.TextField(blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["amount"]
        verbose_name = "devis"
        verbose_name_plural = "devis"
        constraints = [
            models.UniqueConstraint(fields=["request", "pro"], name="un_devis_par_pro"),
        ]

    def __str__(self):
        return f"Devis {self.amount} F CFA ({self.pro})"


class Review(models.Model):
    request = models.OneToOneField(ServiceRequest, on_delete=models.CASCADE, related_name="review")
    rating = models.PositiveSmallIntegerField(
        "note", validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    comment = models.TextField("commentaire", blank=True)
    is_hidden = models.BooleanField(
        "masqué", default=False, help_text="Masqué par l'équipe : hors du site et de la note."
    )
    hidden_reason = models.CharField("motif du masquage", max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "avis"
        verbose_name_plural = "avis"

    def __str__(self):
        return f"{self.rating}/5 — {self.request}"


class Dispute(models.Model):
    """Litige sur une mission réservée ou terminée. Suivi par l'équipe dans la console."""

    class Reason(models.TextChoices):
        NO_SHOW = "no_show", "Pro absent ou très en retard"
        QUALITY = "quality", "Travail mal fait ou inachevé"
        PRICE = "price", "Prix différent du devis"
        BEHAVIOUR = "behaviour", "Comportement"
        DAMAGE = "damage", "Dégât chez le client"
        PAYMENT = "payment", "Paiement non reçu"
        OTHER = "other", "Autre"

    class Status(models.TextChoices):
        OPEN = "open", "Ouvert"
        INVESTIGATING = "investigating", "En cours"
        RESOLVED = "resolved", "Résolu"
        DISMISSED = "dismissed", "Sans suite"

    request = models.ForeignKey(ServiceRequest, on_delete=models.CASCADE, related_name="disputes")
    opened_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="disputes_opened"
    )
    reason = models.CharField("motif", max_length=20, choices=Reason.choices)
    description = models.TextField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)
    resolution = models.TextField("décision", blank=True)
    handled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "litige"

    def __str__(self):
        return f"Litige #{self.pk} — {self.request}"

    @property
    def is_closed(self) -> bool:
        return self.status in (self.Status.RESOLVED, self.Status.DISMISSED)


class RequestEvent(models.Model):
    """Journal des transitions d'une demande (affiché comme historique)."""

    request = models.ForeignKey(ServiceRequest, on_delete=models.CASCADE, related_name="events")
    status = models.CharField(max_length=10, choices=ServiceRequest.Status.choices)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True
    )
    note = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]
        verbose_name = "événement"

    def __str__(self):
        return f"{self.request_id} → {self.status}"


class Coupon(models.Model):
    """Code promo : réduit ce que le client paie. La remise est financée par Jeflink."""

    class Kind(models.TextChoices):
        PERCENT = "percent", "Pourcentage"
        FIXED = "fixed", "Montant fixe"

    code = models.CharField(max_length=20, unique=True, help_text="Majuscules, sans espaces.")
    description = models.CharField(max_length=160, blank=True)
    kind = models.CharField("type", max_length=10, choices=Kind.choices, default=Kind.FIXED)
    value = models.PositiveIntegerField(
        "valeur", help_text="% (1 à 100) ou montant en F CFA selon le type."
    )
    max_discount = models.PositiveIntegerField(
        "remise maximum (F CFA)", null=True, blank=True, help_text="Pour un pourcentage."
    )
    min_amount = models.PositiveIntegerField("devis minimum (F CFA)", null=True, blank=True)
    starts_at = models.DateTimeField("début", null=True, blank=True)
    ends_at = models.DateTimeField("fin", null=True, blank=True)
    max_uses = models.PositiveIntegerField("utilisations maximum", null=True, blank=True)
    max_uses_per_client = models.PositiveSmallIntegerField("par client", default=1)
    first_order_only = models.BooleanField("première commande seulement", default=False)
    trades = models.ManyToManyField(
        "catalog.Trade", blank=True, related_name="coupons", verbose_name="métiers"
    )
    zones = models.ManyToManyField(
        "catalog.Zone", blank=True, related_name="coupons", verbose_name="quartiers"
    )
    is_active = models.BooleanField("actif", default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "code promo"
        verbose_name_plural = "codes promo"

    def __str__(self):
        return self.code
