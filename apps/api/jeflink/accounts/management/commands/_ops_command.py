"""Base commune des commandes Ops (S3, I9).

Deux opérateurs sont exigés : des comptes Admin actifs (rôle ops + groupe Admin), désignés
par leur ``public_id``, distincts entre eux et du compte visé. Seule exception : ``--bootstrap``
crée le tout premier Admin tant qu'il n'en existe aucun ; les opérateurs sont alors nommés.
"""

import os
import uuid
from argparse import ArgumentParser

from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand, CommandError

from jeflink.accounts.models import Role, User
from jeflink.accounts.phone import normalize_phone
from jeflink.common.errors import DomainError
from jeflink.trust.models import AuditEvent
from jeflink.trust.services import audit

OPS_GROUPS = ("Support", "Validation KYC", "Finance", "Admin")
ADMIN_GROUP = "Admin"


def admin_exists() -> bool:
    return User.objects.filter(
        groups__name=ADMIN_GROUP,
        role_grants__role=Role.OPS,
        role_grants__revoked_at__isnull=True,
        is_active=True,
        deleted_at__isnull=True,
    ).exists()


class OpsCommand(BaseCommand):
    reasons: tuple[str, ...] = ()
    allow_bootstrap = False

    def add_arguments(self, parser: ArgumentParser) -> None:
        target = parser.add_mutually_exclusive_group(required=True)
        target.add_argument("--user", help="public_id du compte visé (évite le numéro en clair).")
        target.add_argument("--phone", help="Numéro du compte visé.")
        parser.add_argument("--operator", required=True, help="public_id du premier Admin.")
        parser.add_argument("--second-operator", required=True, help="public_id du second Admin.")
        parser.add_argument("--reason", required=True, choices=self.reasons)
        if self.allow_bootstrap:
            parser.add_argument(
                "--bootstrap",
                action="store_true",
                help="Premier Admin : permis seulement tant qu'aucun Admin n'existe.",
            )

    def get_target(self, options: dict) -> User:
        if options.get("user"):
            try:
                lookup = {"public_id": uuid.UUID(options["user"])}
            except ValueError as exc:
                raise CommandError("--user : public_id invalide.") from exc
        else:
            try:
                lookup = {"phone": normalize_phone(options["phone"])}
            except DomainError as exc:
                raise CommandError(exc.code) from exc
        user = User.objects.filter(**lookup, deleted_at__isnull=True).first()
        if user is None:
            # Le compte doit exister : la personne s'est connectée au moins une fois (consentement).
            raise CommandError("Aucun compte actif ne correspond.")
        return user

    def get_operators(self, options: dict, target: User) -> tuple[str, str, bool]:
        """Renvoie (opérateur, second opérateur, bootstrap) après contrôle."""
        first, second = options["operator"].strip(), options["second_operator"].strip()
        if options.get("bootstrap"):
            if admin_exists():
                raise CommandError("--bootstrap refusé : un Admin existe déjà.")
            if not first or first.lower() == second.lower():
                raise CommandError("Deux opérateurs distincts sont exigés.")
            return first, second, True
        admins = []
        for raw in (first, second):
            try:
                public_id = uuid.UUID(raw)
            except ValueError as exc:
                raise CommandError("Les opérateurs sont désignés par leur public_id.") from exc
            admin = User.objects.filter(
                public_id=public_id,
                groups__name=ADMIN_GROUP,
                role_grants__role=Role.OPS,
                role_grants__revoked_at__isnull=True,
                is_active=True,
                deleted_at__isnull=True,
            ).first()
            if admin is None:
                raise CommandError("Chaque opérateur doit être un Admin actif.")
            admins.append(admin)
        if admins[0].pk == admins[1].pk:
            raise CommandError("Les deux opérateurs doivent être distincts.")
        if target.pk in {admins[0].pk, admins[1].pk}:
            raise CommandError("Un opérateur ne peut pas agir sur son propre compte.")
        return str(admins[0].public_id), str(admins[1].public_id), False

    def audit_groups(
        self,
        *,
        target: User,
        added: list[str],
        removed: list[str],
        operators: tuple[str, str, bool],
        reason: str,
    ) -> None:
        operator, second_operator, bootstrap = operators
        audit(
            action="accounts.ops_groups.changed",
            actor_kind=AuditEvent.ActorKind.OPS,
            target=target,
            metadata={
                "groups_added": sorted(added),
                "groups_removed": sorted(removed),
                "operator": operator,
                "second_operator": second_operator,
                "reason_code": reason,
                "bootstrap": bootstrap,
            },
        )

    # --- Jeton d'enrôlement TOTP (revue sécurité tâche 13, M2) ----------------------------------
    # Jamais écrit sur une sortie non interactive (job, CI, journaux de conteneur) : soit un
    # terminal, soit un fichier créé en 0600 et remis hors bande.

    @staticmethod
    def add_token_file_argument(parser: ArgumentParser) -> None:
        parser.add_argument(
            "--token-file",
            help="Fichier (créé en 0600, jamais écrasé) qui recevra le jeton d'enrôlement TOTP.",
        )

    def check_token_destination(self, options: dict) -> None:
        """Avant toute écriture : refuse d'émettre un jeton qui finirait dans un journal."""
        path = options.get("token_file")
        if path:
            if os.path.exists(path):
                raise CommandError("--token-file : le fichier existe déjà.")
        elif not self.stdout.isatty():
            raise CommandError("Hors terminal, --token-file est obligatoire (jeton d'enrôlement).")

    def deliver_token(
        self,
        options: dict,
        token: str,
        label: str = "Jeton d'enrôlement TOTP (24 h, usage unique)",
    ) -> None:
        path = options.get("token_file")
        if path:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(f"{token}\n")
            self.stdout.write(f"{label} : écrit dans {path}.")
        else:
            self.stdout.write(f"{label} : {token}")

    @staticmethod
    def resolve_groups(names: list[str]) -> list[Group]:
        groups = list(Group.objects.filter(name__in=names))
        if len(groups) != len(set(names)):
            raise CommandError("Un groupe demandé n'existe pas en base (migrations appliquées ?).")
        return groups
