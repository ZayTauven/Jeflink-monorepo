"""Accorde le rôle ops et des groupes Ops. Seul moyen de créer un Ops (spec 001, S1 et S3).

Exemple : manage.py grant_ops_role --user <public_id> --groups Support \
          --operator <public_id Admin> --second-operator <public_id Admin> --reason hiring
Premier Admin : ajouter --bootstrap ; les opérateurs sont alors des noms.
"""

from argparse import ArgumentParser

from django.core.management.base import CommandError
from django.db import transaction

from jeflink.accounts.models import Role
from jeflink.accounts.services import grant_role
from jeflink.common.errors import DomainError
from jeflink.common.pii import mask_phone

from ._ops_command import ADMIN_GROUP, OPS_GROUPS, OpsCommand


class Command(OpsCommand):
    help = "Accorde le rôle ops (audité, deux Admin)."
    reasons = ("hiring", "role_change", "bootstrap")
    allow_bootstrap = True

    def add_arguments(self, parser: ArgumentParser) -> None:
        super().add_arguments(parser)
        parser.add_argument(
            "--groups", required=True, help=f"Groupes séparés par des virgules : {OPS_GROUPS}."
        )

    def handle(self, *args, **options) -> None:
        names = sorted({name.strip() for name in options["groups"].split(",") if name.strip()})
        if not names or set(names) - set(OPS_GROUPS):
            raise CommandError(f"Groupes inconnus ou absents. Choix : {', '.join(OPS_GROUPS)}.")
        if options.get("bootstrap") and (
            options["reason"] != "bootstrap" or ADMIN_GROUP not in names
        ):
            raise CommandError("--bootstrap exige --reason bootstrap et le groupe Admin.")
        target = self.get_target(options)
        operators = self.get_operators(options, target)
        groups = self.resolve_groups(names)
        with transaction.atomic():
            try:
                grant_role(
                    user=target,
                    role=Role.OPS,
                    reason_code=options["reason"],
                    operator=operators[0],
                    second_operator=operators[1],
                )
            except DomainError as exc:
                raise CommandError(exc.code) from exc
            current = set(target.groups.values_list("name", flat=True))
            target.groups.add(*groups)
            self.audit_groups(
                target=target,
                added=[g.name for g in groups if g.name not in current],
                removed=[],
                operators=operators,
                reason=options["reason"],
            )
        self.stdout.write(f"Rôle ops accordé à {mask_phone(target.phone)} ({', '.join(names)}).")
