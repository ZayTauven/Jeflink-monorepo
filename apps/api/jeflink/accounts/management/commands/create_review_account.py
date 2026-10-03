"""Crée (ou retrouve) le compte de revue des stores et lui donne un nouveau code (S17).

À lancer à chaque soumission Apple ou Google. Deux Admin, motif énuméré, audité. Le numéro
doit figurer dans ``OTP_REVIEW_ACCOUNTS`` (SIM détenue par Jeflink). Un compte réel existant
sur ce numéro n'est jamais transformé en compte de revue.

Exemple : manage.py create_review_account --phone +22177… --operator <Admin> \\
          --second-operator <Admin> --reason store_submission --token-file /chemin/code.txt
"""

from argparse import ArgumentParser

from django.core.management.base import CommandError
from django.db import transaction
from django.utils import timezone

from jeflink.accounts.models import User
from jeflink.accounts.otp_limits import unblock_phone
from jeflink.accounts.phone import normalize_phone
from jeflink.accounts.review_accounts import is_review_phone, review_until, rotate_code
from jeflink.accounts.validators import clean_display_name
from jeflink.common.errors import DomainError
from jeflink.common.pii import mask_phone
from jeflink.trust.models import AuditEvent
from jeflink.trust.services import audit

from ._ops_command import OpsCommand

DEFAULT_NAME = "Awa Ndiaye"


class Command(OpsCommand):
    help = "Crée le compte de revue des stores et change son code (deux Admin, audité)."
    reasons = ("store_submission", "code_rotation")

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("--phone", required=True, help="Numéro listé dans OTP_REVIEW_ACCOUNTS.")
        parser.add_argument("--operator", required=True, help="public_id du premier Admin.")
        parser.add_argument("--second-operator", required=True, help="public_id du second Admin.")
        parser.add_argument("--reason", required=True, choices=self.reasons)
        parser.add_argument(
            "--display-name", default=DEFAULT_NAME, help="Nom affiché (fictif) du compte de revue."
        )
        self.add_token_file_argument(parser)

    def handle(self, *args, **options) -> None:
        try:
            phone = normalize_phone(options["phone"])
        except DomainError as exc:
            raise CommandError(exc.code) from exc
        if not is_review_phone(phone):
            raise CommandError("Ce numéro ne figure pas dans OTP_REVIEW_ACCOUNTS.")
        until = review_until()
        if until is None or until <= timezone.now():
            raise CommandError("OTP_REVIEW_ENABLED_UNTIL absent ou passé : aucune revue ouverte.")
        try:
            display_name = clean_display_name(options["display_name"])
        except DomainError as exc:
            raise CommandError(f"--display-name : {exc.code}") from exc
        self.check_token_destination(options)
        with transaction.atomic():
            user = User.objects.select_for_update(no_key=True).filter(phone=phone).first()
            created = user is None
            if created:
                user = User.objects.create_user(
                    phone,
                    is_review_account=True,
                    display_name=display_name,
                    profile_status=User.ProfileStatus.COMPLETE,
                    phone_verified_at=timezone.now(),
                )
            elif not user.is_review_account:
                raise CommandError("Un compte réel utilise ce numéro : jamais transformé.")
            operator, second_operator, _ = self.get_operators(options, user)
            if created:
                audit(
                    action="accounts.review_account.created",
                    actor_kind=AuditEvent.ActorKind.OPS,
                    target=user,
                    metadata={
                        "operator": operator,
                        "second_operator": second_operator,
                        "reason_code": options["reason"],
                    },
                )
            code = rotate_code(
                user=user,
                operator=operator,
                second_operator=second_operator,
                reason_code=options["reason"],
            )
            # Un tiers a pu bloquer le numéro par de mauvais codes : levé à chaque soumission (I2).
            unblock_phone(phone, actor=None, reason_code="review_rotation", target=user)
        state = "créé" if created else "retrouvé"
        self.stdout.write(f"Compte de revue {state} : {mask_phone(phone)}, actif jusqu'au {until}.")
        # Remis une seule fois, jamais journalisé ; à saisir dans la fiche de soumission du store.
        self.deliver_token(options, code, label="Code du compte de revue")
