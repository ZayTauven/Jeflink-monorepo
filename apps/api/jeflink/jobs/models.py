from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class ServiceRequest(models.Model):
    """Demande d'un client. Le statut ne change que par ``jobs.services.transition``."""

    class Status(models.TextChoices):
        OPEN = "open", "En attente de devis"
        BOOKED = "booked", "Pro réservé"
        DONE = "done", "Terminée"
        CANCELLED = "cancelled", "Annulée"

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
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "avis"
        verbose_name_plural = "avis"

    def __str__(self):
        return f"{self.rating}/5 — {self.request}"


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
