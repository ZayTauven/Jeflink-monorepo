"""Réinitialise le second facteur d'un Ops (téléphone perdu, verrou). Deux Admin, audité (S1).

Supprime le TOTP, invalide les challenges MFA et les sessions console, puis affiche une seule
fois un nouveau jeton d'enrôlement (24 h, usage unique) à remettre hors bande.
"""

from django.core.management.base import CommandError

from jeflink.accounts.mfa import reset_totp
from jeflink.accounts.models import Role
from jeflink.accounts.selectors import has_role
from jeflink.common.pii import mask_phone

from ._ops_command import OpsCommand


class Command(OpsCommand):
    help = "Réinitialise le TOTP d'un Ops et émet un jeton d'enrôlement (audité, deux Admin)."
    reasons = ("device_lost", "device_changed", "mfa_locked", "security_incident")

    def handle(self, *args, **options) -> None:
        target = self.get_target(options)
        operator, second_operator, _ = self.get_operators(options, target)
        if not has_role(target, Role.OPS):
            raise CommandError("Le compte visé n'a pas le rôle ops.")
        token = reset_totp(
            user=target,
            operator=operator,
            second_operator=second_operator,
            reason_code=options["reason"],
        )
        self.stdout.write(f"Second facteur réinitialisé pour {mask_phone(target.phone)}.")
        # Affiché une seule fois, jamais journalisé : à remettre hors bande (S1).
        self.stdout.write(f"Jeton d'enrôlement TOTP (24 h, usage unique) : {token}")
