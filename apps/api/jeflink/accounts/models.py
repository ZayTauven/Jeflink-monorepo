from django.contrib.auth.models import AbstractUser


class User(AbstractUser):
    """Modèle utilisateur propre au projet, posé avant la première migration.

    Volontairement minimal : téléphone E.164 comme identifiant, rôles (client, owner,
    technician, ops) et OTP arriveront avec la spec accounts.
    """
