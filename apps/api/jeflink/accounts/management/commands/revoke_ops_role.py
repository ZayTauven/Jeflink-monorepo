"""Retire le rôle ops et tous les groupes Ops d'un compte (audité, deux opérateurs)."""

from django.contrib.auth.models import Group
from django.db import transaction

from jeflink.accounts.models import Role
from jeflink.accounts.services import revoke_role
from jeflink.common.pii import mask_phone

from ._ops_command import OPS_GROUPS, OpsCommand


class Command(OpsCommand):
    help = "Retire le rôle ops (audité, deux opérateurs)."

    def handle(self, *args, **options) -> None:
        self.check_operators(options)
        user = self.get_user(options["phone"])
        with transaction.atomic():
            revoked = revoke_role(
                user=user,
                role=Role.OPS,
                reason_code=options["reason"],
                operator=options["operator"],
                second_operator=options["second_operator"],
            )
            user.groups.remove(*Group.objects.filter(name__in=OPS_GROUPS))
        state = "retiré" if revoked else "déjà absent"
        self.stdout.write(f"Rôle ops {state} pour {mask_phone(user.phone)}.")
