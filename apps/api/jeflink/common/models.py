import uuid

from django.db import models


class BaseModel(models.Model):
    """Base de tous les modèles métier : l'id entier ne sort jamais de l'API, seul public_id."""

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
