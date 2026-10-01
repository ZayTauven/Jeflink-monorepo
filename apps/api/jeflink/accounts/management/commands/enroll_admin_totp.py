"""Enrôle (ou réenrôle) le second facteur d'un compte technique de l'admin Django (tâche 21).

Deux Admin, motif énuméré, audité. L'URI ``otpauth://`` est remise une seule fois (terminal ou
fichier 0600) ; le premier code valide saisi à la connexion confirme l'appareil. Un réenrôlement
remplace l'ancien secret.
"""

from argparse import ArgumentParser

import pyotp
from django.core.management.base import CommandError
from django.db import transaction

from jeflink.accounts.mfa import OTPAUTH_LABEL, TOTP_DIGITS, TOTP_INTERVAL, _fernet
from jeflink.accounts.models import TotpDevice
from jeflink.common.pii import mask_phone
from jeflink.trust.models import AuditEvent
from jeflink.trust.services import audit

from ._ops_command import OpsCommand


class Command(OpsCommand):
    help = "Enrôle le TOTP d'un compte technique de l'admin Django (deux Admin, audité)."
    reasons = ("new_staff", "device_lost", "device_changed", "security_incident")

    def add_arguments(self, parser: ArgumentParser) -> None:
        super().add_arguments(parser)
        self.add_token_file_argument(parser)

    def handle(self, *args, **options) -> None:
        target = self.get_target(options)
        if not target.is_staff:
            raise CommandError("Le compte visé n'est pas un compte technique (is_staff).")
        operator, second_operator, _ = self.get_operators(options, target)
        self.check_token_destination(options)
        secret = pyotp.random_base32(length=32)
        with transaction.atomic():
            TotpDevice.objects.filter(user=target).delete()
            TotpDevice.objects.create(
                user=target, secret_encrypted=_fernet().encrypt(secret.encode()).decode()
            )
            audit(
                action="accounts.admin.totp_issued",
                actor_kind=AuditEvent.ActorKind.OPS,
                target=target,
                metadata={
                    "operator": operator,
                    "second_operator": second_operator,
                    "reason_code": options["reason"],
                },
            )
        uri = pyotp.TOTP(secret, digits=TOTP_DIGITS, interval=TOTP_INTERVAL).provisioning_uri(
            name=f"Admin {OTPAUTH_LABEL}", issuer_name="Jeflink"
        )
        self.stdout.write(f"Second facteur admin émis pour {mask_phone(target.phone)}.")
        self.deliver_token(options, uri, label="URI otpauth de l'admin (à scanner, usage unique)")
