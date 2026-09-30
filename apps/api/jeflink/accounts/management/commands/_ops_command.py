"""Base commune des commandes Ops : deux opérateurs distincts et un motif, recopiés dans l'audit."""

from argparse import ArgumentParser

from django.core.management.base import BaseCommand, CommandError

from jeflink.accounts.models import User
from jeflink.accounts.phone import normalize_phone
from jeflink.common.errors import DomainError
from jeflink.common.pii import mask_phone

OPS_GROUPS = ("Support", "Validation KYC", "Finance", "Admin")


class OpsCommand(BaseCommand):
    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("--phone", required=True, help="Numéro du compte visé.")
        parser.add_argument("--operator", required=True, help="Identifiant de l'opérateur.")
        parser.add_argument(
            "--second-operator", required=True, help="Second opérateur Admin, distinct."
        )
        parser.add_argument("--reason", required=True, help="Code du motif (ex. hiring).")

    def check_operators(self, options: dict) -> None:
        if options["operator"].strip().lower() == options["second_operator"].strip().lower():
            raise CommandError("--second-operator doit être distinct de --operator.")

    def get_user(self, raw_phone: str) -> User:
        try:
            phone = normalize_phone(raw_phone)
        except DomainError as exc:
            raise CommandError(exc.code) from exc
        user = User.objects.filter(phone=phone, deleted_at__isnull=True).first()
        if user is None:
            # Le compte doit exister : la personne s'est connectée au moins une fois (consentement).
            raise CommandError(f"Aucun compte actif pour {mask_phone(phone)}.")
        return user
