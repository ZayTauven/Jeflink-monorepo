"""Réinitialise le second facteur d'un Ops (téléphone perdu, verrou). Deux Admin, audité (S1).

Supprime le TOTP, invalide les challenges MFA et les sessions console, puis affiche une seule
fois un nouveau jeton d'enrôlement (24 h, usage unique) à remettre hors bande.
"""

from argparse import ArgumentParser

from django.core.management.base import CommandError

from jeflink.accounts.mfa import reset_totp
from jeflink.accounts.models import Role
from jeflink.accounts.selectors import has_role
from jeflink.common.pii import mask_phone

from ._ops_command import OpsCommand


class Command(OpsCommand):
    help = "Réinitialise le TOTP d'un Ops et émet un jeton d'enrôlement (audité, deux Admin)."
    reasons = ("device_lost", "device_changed", "mfa_locked", "security_incident")

    def add_arguments(self, parser: ArgumentParser) -> None:
        super().add_arguments(parser)
        self.add_token_file_argument(parser)

    def handle(self, *args, **options) -> None:
        target = self.get_target(options)
        operator, second_operator, _ = self.get_operators(options, target)
        if not has_role(target, Role.OPS):
            raise CommandError("Le compte visé n'a pas le rôle ops.")
        self.check_token_destination(options)
        token = reset_totp(
            user=target,
            operator=operator,
            second_operator=second_operator,
            reason_code=options["reason"],
        )
        self.stdout.write(f"Second facteur réinitialisé pour {mask_phone(target.phone)}.")
        # Remis une seule fois, jamais journalisé : à transmettre hors bande (S1).
        self.deliver_token(options, token)
