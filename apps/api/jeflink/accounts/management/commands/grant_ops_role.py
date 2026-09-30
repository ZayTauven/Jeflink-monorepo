"""Accorde le rôle ops et des groupes Ops. Seul moyen de créer un Ops (spec 001, S1 et S3).

Exemple : manage.py grant_ops_role --phone 771234567 --groups Support \
          --operator zay --second-operator awa --reason hiring
"""

from argparse import ArgumentParser

from django.contrib.auth.models import Group
from django.core.management.base import CommandError
from django.db import transaction

from jeflink.accounts.models import Role
from jeflink.accounts.services import grant_role
from jeflink.common.errors import DomainError
from jeflink.common.pii import mask_phone

from ._ops_command import OPS_GROUPS, OpsCommand


class Command(OpsCommand):
    help = "Accorde le rôle ops (audité, deux opérateurs)."

    def add_arguments(self, parser: ArgumentParser) -> None:
        super().add_arguments(parser)
        parser.add_argument(
            "--groups", required=True, help=f"Groupes séparés par des virgules : {OPS_GROUPS}."
        )

    def handle(self, *args, **options) -> None:
        self.check_operators(options)
        names = [name.strip() for name in options["groups"].split(",") if name.strip()]
        unknown = set(names) - set(OPS_GROUPS)
        if not names or unknown:
            raise CommandError(f"Groupes inconnus ou absents. Choix : {', '.join(OPS_GROUPS)}.")
        user = self.get_user(options["phone"])
        with transaction.atomic():
            try:
                grant_role(
                    user=user,
                    role=Role.OPS,
                    reason_code=options["reason"],
                    operator=options["operator"],
                    second_operator=options["second_operator"],
                )
            except DomainError as exc:
                raise CommandError(exc.code) from exc
            user.groups.add(*Group.objects.filter(name__in=names))
        self.stdout.write(f"Rôle ops accordé à {mask_phone(user.phone)} ({', '.join(names)}).")
