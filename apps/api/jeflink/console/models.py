from django.conf import settings
from django.db import models


class AuditLog(models.Model):
    """Journal des actions de l'équipe dans la console : qui a fait quoi, sur quoi, quand."""

    class Action(models.TextChoices):
        PRO_VERIFY = "pro.verify", "Pro vérifié"
        PRO_REJECT = "pro.reject", "Vérification refusée"
        USER_SUSPEND = "user.suspend", "Compte suspendu"
        USER_REACTIVATE = "user.reactivate", "Compte réactivé"
        REQUEST_CANCEL = "request.cancel", "Demande annulée par l'équipe"
        REQUEST_NOTE = "request.note", "Note interne modifiée"
        REVIEW_HIDE = "review.hide", "Avis masqué"
        REVIEW_SHOW = "review.show", "Avis rétabli"
        CONTACT_HANDLE = "contact.handle", "Message traité"
        CONTACT_REOPEN = "contact.reopen", "Message rouvert"
        DISPUTE_OPEN = "dispute.open", "Litige ouvert"
        DISPUTE_UPDATE = "dispute.update", "Litige mis à jour"

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+"
    )
    action = models.CharField(max_length=30, choices=Action.choices)
    target_type = models.CharField("type de cible", max_length=20)
    target_id = models.PositiveIntegerField()
    target_label = models.CharField("cible", max_length=200)
    details = models.CharField("précisions", max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        verbose_name = "action de l'équipe"
        verbose_name_plural = "journal d'audit"

    def __str__(self):
        return f"{self.get_action_display()} — {self.target_label}"
