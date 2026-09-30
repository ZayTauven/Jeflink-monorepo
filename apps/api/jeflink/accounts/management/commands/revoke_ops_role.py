"""Retire le rôle ops et tous les groupes Ops d'un compte (audité, deux Admin)."""

from django.db import transaction

from jeflink.accounts.mfa import clear_mfa
from jeflink.accounts.models import DeviceSession, Role, User
from jeflink.accounts.services import revoke_role
from jeflink.accounts.sessions import revoke_all_sessions
from jeflink.common.pii import mask_phone

from ._ops_command import OPS_GROUPS, OpsCommand


class Command(OpsCommand):
    help = "Retire le rôle ops (audité, deux Admin)."
    reasons = ("departure", "role_change", "security_incident")

    def handle(self, *args, **options) -> None:
        target = self.get_target(options)
        operators = self.get_operators(options, target)
        with transaction.atomic():
            # Verrou du compte d'abord : même ordre que le module mfa.
            User.objects.select_for_update(no_key=True).get(pk=target.pk)
            revoked = revoke_role(
                user=target,
                role=Role.OPS,
                reason_code=options["reason"],
                operator=operators[0],
                second_operator=operators[1],
            )
            removed = list(target.groups.filter(name__in=OPS_GROUPS).values_list("name", flat=True))
            target.groups.remove(*target.groups.filter(name__in=OPS_GROUPS))
            # Politique de session changée (console_ops) : sessions console révoquées (I2, S1).
            revoke_all_sessions(
                user=target, reason=DeviceSession.RevokedReason.OPS_ROLE_CHANGED, app="console"
            )
            # Un rôle rendu plus tard exigera un nouvel enrôlement hors bande (revue, M1).
            clear_mfa(target)
            self.audit_groups(
                target=target,
                added=[],
                removed=removed,
                operators=operators,
                reason=options["reason"],
            )
        state = "retiré" if revoked else "déjà absent"
        self.stdout.write(f"Rôle ops {state} pour {mask_phone(target.phone)}.")
