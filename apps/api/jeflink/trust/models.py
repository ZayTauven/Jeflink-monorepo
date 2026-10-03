import uuid

from django.conf import settings
from django.db import models

from jeflink.common.models import BaseModel


class AppendOnlyQuerySet(models.QuerySet):
    """Refuse les mises à jour et suppressions en masse (la base les refuse aussi, par trigger)."""

    def update(self, **kwargs):
        raise PermissionError("AuditEvent est en ajout seul.")

    def delete(self):
        raise PermissionError("AuditEvent est en ajout seul.")


class AuditEvent(models.Model):
    """Journal d'audit en ajout seul : ni modification, ni suppression par l'application.

    ``actor_public_id`` est toujours renseigné quand il y a un acteur. La clé étrangère
    ``actor`` ne l'est que pour les écritures ordinaires : une écriture durable (connexion
    ``audit``) n'en pose pas, pour ne jamais attendre un verrou tenu par l'appelant (S15).
    """

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
    actor_public_id = models.UUIDField(null=True, blank=True, db_index=True)
    actor_kind = models.CharField(max_length=8, choices=ActorKind.choices)
    action = models.CharField(max_length=64, db_index=True)
    target_type = models.CharField(max_length=64, blank=True)
    target_public_id = models.UUIDField(null=True, blank=True, db_index=True)
    session_public_id = models.UUIDField(null=True, blank=True)
    request_id = models.CharField(max_length=64, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    objects = AppendOnlyQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            # Une action « user » a toujours un acteur. Une action « ops » lancée par une
            # commande de gestion peut ne pas en avoir : l'opérateur figure dans les métadonnées.
            models.CheckConstraint(
                condition=~models.Q(actor_kind="user") | models.Q(actor_public_id__isnull=False),
                name="audit_user_action_has_actor_id",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.action} · {self.created_at:%Y-%m-%d %H:%M}"

    def save(self, *args, **kwargs) -> None:
        if not self._state.adding:
            raise PermissionError("AuditEvent est en ajout seul.")
        kwargs["force_insert"] = True
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise PermissionError("AuditEvent est en ajout seul.")


DISPUTE_DESCRIPTION_MIN = 10
DISPUTE_DESCRIPTION_MAX = 1000
DISPUTE_NOTE_MAX = 500


class Dispute(BaseModel):
    """Litige ouvert par le client avant la fin de la fenêtre de contestation (spec 004).

    Jeflink examine et décide : pas de remboursement en V1. La description (texte libre du client)
    et la note de décision de l'Ops ne sont jamais écrites dans un log ni un audit. Le modèle vit
    ici (``ARCHITECTURE.md`` y range litiges et garantie) : ``bookings.services`` appelle
    ``trust.services``, jamais l'inverse.
    """

    class Reason(models.TextChoices):
        NOT_DONE = "not_done", "Travail non fait"
        POOR_QUALITY = "poor_quality", "Mauvaise qualité"
        DAMAGE = "damage", "Dégât"
        PRICE = "price", "Prix"
        BEHAVIOUR = "behaviour", "Comportement"
        OTHER = "other", "Autre"

    class Status(models.TextChoices):
        OPEN = "open", "Ouvert"
        RESOLVED = "resolved", "Tranché"

    class Decision(models.TextChoices):
        FOR_CLIENT = "for_client", "En faveur du client"
        FOR_PRO = "for_pro", "En faveur du pro"
        NO_FAULT = "no_fault", "Sans faute"

    booking = models.OneToOneField(
        "bookings.Booking", on_delete=models.PROTECT, related_name="dispute"
    )
    reason = models.CharField(max_length=12, choices=Reason.choices)
    description = models.CharField(max_length=DISPUTE_DESCRIPTION_MAX, blank=True)
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.OPEN)
    decision = models.CharField(max_length=10, choices=Decision.choices, blank=True)
    decision_note = models.CharField(max_length=DISPUTE_NOTE_MAX, blank=True)
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "litige"
        ordering = ("-created_at",)
        permissions = [("decide_dispute", "Médiation : trancher un litige")]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(status="open", decision="")
                | (models.Q(status="resolved") & ~models.Q(decision="")),
                name="dispute_decision_iff_resolved",
            ),
        ]

    def __str__(self) -> str:
        return f"litige {self.status}"
