"""Crée la fiche d'un pro (statut ``pending``) et lui accorde le rôle ``owner`` (spec 003).

Le compte doit exister : la personne s'est connectée au moins une fois (consentement).
L'inscription en libre-service viendra avec l'app Pro (étape 6).

Exemple : manage.py onboard_provider --phone +22177… --name "Plomberie Ibou" \
          --trades plomberie --zones ouakam,almadies --operator <public_id d'un Admin>
"""

import uuid
from argparse import ArgumentParser

from django.core.management.base import BaseCommand, CommandError

from jeflink.accounts.management.commands._ops_command import ADMIN_GROUP
from jeflink.accounts.models import Role, User
from jeflink.accounts.phone import normalize_phone
from jeflink.catalog.models import Trade
from jeflink.common.errors import DomainError
from jeflink.providers.services import onboard_provider
from jeflink.zones.models import Zone


class Command(BaseCommand):
    help = "Crée la fiche d'un pro (pending) et accorde le rôle owner."

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("--phone", required=True, help="Numéro du compte du gérant.")
        parser.add_argument("--name", required=True, help="Nom commercial (60 caractères).")
        parser.add_argument("--trades", required=True, help="Slugs de métiers, séparés par « , ».")
        parser.add_argument("--zones", required=True, help="Slugs de zones, séparés par « , ».")
        parser.add_argument("--operator", required=True, help="public_id d'un Admin actif.")

    @staticmethod
    def _slugs(raw: str) -> list[str]:
        return [item.strip() for item in raw.split(",") if item.strip()]

    def handle(self, *args, **options) -> None:
        try:
            operator = uuid.UUID(options["operator"].strip())
        except ValueError as exc:
            raise CommandError("--operator : public_id invalide.") from exc
        admin = User.objects.filter(
            public_id=operator,
            groups__name=ADMIN_GROUP,
            role_grants__role=Role.OPS,
            role_grants__revoked_at__isnull=True,
            is_active=True,
            deleted_at__isnull=True,
        ).first()
        if admin is None:
            raise CommandError("--operator doit être un Admin actif.")
        try:
            phone = normalize_phone(options["phone"])
        except DomainError as exc:
            raise CommandError(exc.code) from exc
        user = User.objects.filter(phone=phone, deleted_at__isnull=True).first()
        if user is None:
            raise CommandError("Aucun compte actif ne correspond.")
        trade_slugs, zone_slugs = self._slugs(options["trades"]), self._slugs(options["zones"])
        trades = list(Trade.objects.filter(slug__in=trade_slugs))
        zones = list(Zone.objects.filter(slug__in=zone_slugs))
        if len(trades) != len(set(trade_slugs)) or len(zones) != len(set(zone_slugs)):
            raise CommandError("Un métier ou une zone est inconnu.")
        try:
            provider = onboard_provider(
                user=user,
                business_name=options["name"],
                trades=trades,
                zones=zones,
                operator=str(operator),
            )
        except DomainError as exc:
            raise CommandError(exc.code) from exc
        self.stdout.write(f"Pro créé (pending) : {provider.public_id}. À vérifier dans l'admin.")
