"""Canaux de règlement de démonstration (spec 005) : local seulement, numéros factices.

En préproduction et en production, la Comptabilité saisit les vrais canaux dans l'admin.
Idempotent : un canal existant (par slug) n'est jamais modifié.
"""

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from jeflink.payments.models import Gateway, SettlementChannel

DEMO_CHANNELS = [
    {
        "slug": "wave-demo",
        "gateway": Gateway.MANUAL_MOBILE_MONEY,
        "label_fr": "Wave (démo)",
        "label_wo": "Wave (démo)",
        "account_display": "Jeflink · 70 000 00 00 (factice)",
        "instructions_fr": (
            "Envoyez le montant au numéro marchand Jeflink, ou déposez-le chez un agent Wave. "
            "Gardez le SMS de confirmation : il contient la référence à déclarer."
        ),
        "position": 1,
    },
    {
        "slug": "orange-money-demo",
        "gateway": Gateway.MANUAL_MOBILE_MONEY,
        "label_fr": "Orange Money (démo)",
        "label_wo": "Orange Money (démo)",
        "account_display": "Jeflink · 70 000 00 01 (factice)",
        "instructions_fr": (
            "Payez le marchand Jeflink depuis Orange Money ou chez un agent. Gardez le SMS de "
            "confirmation : il contient la référence à déclarer."
        ),
        "position": 2,
    },
    {
        "slug": "caisse-demo",
        "gateway": Gateway.CASH,
        "label_fr": "Espèces au bureau (démo)",
        "label_wo": "Xaalis ci biro bi (démo)",
        "account_display": "Bureau Jeflink",
        "instructions_fr": "Remettez les espèces au bureau : un reçu numéroté vous est remis.",
        "position": 3,
    },
]


class Command(BaseCommand):
    help = "Crée les canaux de règlement de démonstration qui manquent (local seulement)."

    def handle(self, *args, **options) -> None:
        if settings.DJANGO_ENV != "local":
            raise CommandError("Commande de démonstration : refusée hors DJANGO_ENV=local.")
        created = 0
        for data in DEMO_CHANNELS:
            _, was_created = SettlementChannel.objects.get_or_create(
                slug=data["slug"], defaults={k: v for k, v in data.items() if k != "slug"}
            )
            created += was_created
        self.stdout.write(f"{created} canal(aux) de règlement de démonstration créé(s).")
