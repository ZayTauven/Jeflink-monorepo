import uuid

from django.conf import settings
from django.db import models


class AuditEvent(models.Model):
    """Journal d'audit en ajout seul : ni modification, ni suppression par l'application."""

    class ActorKind(models.TextChoices):
        USER = "user"
        OPS = "ops"
        SYSTEM = "system"

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
    )
    actor_kind = models.CharField(max_length=8, choices=ActorKind.choices)
    action = models.CharField(max_length=64, db_index=True)
    target_type = models.CharField(max_length=64, blank=True)
    target_public_id = models.UUIDField(null=True, blank=True, db_index=True)
    session_public_id = models.UUIDField(null=True, blank=True)
    request_id = models.CharField(max_length=64, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            # Une action « user » a toujours un compte acteur. Une action « ops » lancée par une
            # commande de gestion n'en a pas : l'opérateur est nommé dans les métadonnées.
            models.CheckConstraint(
                condition=~models.Q(actor_kind="user") | models.Q(actor__isnull=False),
                name="audit_user_action_has_actor",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.action} · {self.created_at:%Y-%m-%d %H:%M}"

    def save(self, *args, **kwargs) -> None:
        if not self._state.adding:
            raise PermissionError("AuditEvent est en ajout seul.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise PermissionError("AuditEvent est en ajout seul.")
