from django.conf import settings
from django.db import models


class JefSession(models.Model):
    """Un échange avec Jef : le texte du client, les questions, ses réponses, la fiche produite.

    La fiche est rattachée à la demande quand le client la publie : le pro la lit, l'équipe la
    retrouve dans la console (rubrique Jef).
    """

    class Mode(models.TextChoices):
        AI = "ai", "IA (Claude)"
        GUIDE = "guide", "Questions guidées"

    client = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="jef_sessions"
    )
    trade = models.ForeignKey(
        "catalog.Trade", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    text = models.TextField("ce que le client a écrit")
    mode = models.CharField(max_length=8, choices=Mode.choices)
    # [{"id": "q1", "question": "…", "choices": ["…"]}] ; choix vides = réponse libre.
    questions = models.JSONField(default=list)
    answers = models.JSONField(default=dict)
    # {"title", "description", "urgent", "client_tips", "pro_summary", "pro_details", "pro_bring"}
    brief = models.JSONField(null=True, blank=True)
    request = models.OneToOneField(
        "jobs.ServiceRequest",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="jef_session",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "échange avec Jef"
        verbose_name_plural = "échanges avec Jef"

    def __str__(self) -> str:
        return f"Jef n° {self.pk} ({self.get_mode_display()})"
