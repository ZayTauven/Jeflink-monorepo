"""Données de départ du catalogue et des zones (spec 002). Idempotent : relançable sans risque.

Crée ce qui manque (par slug) et n'écrase jamais une saisie de l'admin. En local, les métiers
sont ouverts dans toutes les zones créées ; ailleurs, l'Ops les ouvre (« Ouvrir partout »).
"""

from django.conf import settings
from django.core.management.base import BaseCommand

from jeflink.catalog.services import seed_trades
from jeflink.zones.services import seed_zones


class Command(BaseCommand):
    help = "Crée les métiers, services, la ville et les zones de départ qui manquent."

    def add_arguments(self, parser):
        parser.add_argument(
            "--open-trades",
            action="store_true",
            default=None,
            help="Ouvre tous les métiers dans les zones créées (défaut : seulement en local).",
        )
        parser.add_argument("--no-open-trades", dest="open_trades", action="store_false")

    def handle(self, *args, **options):
        open_trades = options["open_trades"]
        if open_trades is None:
            open_trades = settings.DJANGO_ENV == "local"
        trades, services = seed_trades()
        zones = seed_zones(open_trades=open_trades)
        self.stdout.write(
            f"{trades} métier(s), {services} service(s), {zones} zone(s) créé(s)"
            + (" ; métiers ouverts dans les nouvelles zones." if open_trades and zones else ".")
        )
