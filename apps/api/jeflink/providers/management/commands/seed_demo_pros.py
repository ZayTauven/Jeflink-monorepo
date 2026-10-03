"""Crée trois pros de démonstration vérifiés (local seulement, spec 003). Idempotent.

Ils couvrent les métiers et les zones du seed de la spec 002 (``seed_reference_data``) et servent
au parcours de bout en bout sans Ops : ``demo_pro autoquote`` leur fait envoyer des devis. Tout
passe par les services (``onboard_provider``, ``set_status``) ; ``is_demo`` les isole des vrais
pros (contrôle au démarrage hors local/test).
"""

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from jeflink.accounts.models import User
from jeflink.catalog.models import Trade
from jeflink.common.errors import DomainError
from jeflink.providers.models import Provider
from jeflink.providers.services import onboard_provider, set_status
from jeflink.zones.models import Zone

# Numéros fictifs et noms de démonstration : jamais de vraie personne.
DEMO_PROS = [
    ("+221770009001", "Awa Démo", "Plomberie Ibou (démo)"),
    ("+221770009002", "Moussa Démo", "Électricité Moussa (démo)"),
    ("+221770009003", "Fatou Démo", "Dépannage Fatou (démo)"),
]


def require_local() -> None:
    if settings.DJANGO_ENV != "local":
        raise CommandError("Commande de démonstration : refusée hors DJANGO_ENV=local.")


class Command(BaseCommand):
    help = "Crée 3 pros de démonstration vérifiés (local seulement, idempotent)."

    def handle(self, *args, **options) -> None:
        require_local()
        trades = list(Trade.objects.filter(is_active=True))
        zones = list(Zone.objects.filter(is_active=True, city__is_active=True))
        if not trades or not zones:
            raise CommandError("Aucun métier ou aucune zone : lancez d'abord `make seed`.")
        created = 0
        for phone, name, business in DEMO_PROS:
            user = User.objects.filter(phone=phone).first() or User.objects.create_user(
                phone, display_name=name, profile_status=User.ProfileStatus.COMPLETE
            )
            provider = Provider.objects.filter(owner=user).first()
            try:
                if provider is None:
                    provider = onboard_provider(
                        user=user,
                        business_name=business,
                        trades=trades,
                        zones=zones,
                        operator="seed_demo_pros",
                        is_demo=True,
                    )
                    created += 1
                if provider.status != Provider.Status.VERIFIED:
                    set_status(
                        provider=provider, to=Provider.Status.VERIFIED, actor=None,
                        reason="seed_demo_pros",
                    )  # fmt: skip
            except DomainError as exc:
                raise CommandError(exc.code) from exc
            # Les métiers et zones ajoutés depuis suivent : la démo couvre tout le catalogue.
            provider.trades.set(trades)
            provider.zones.set(zones)
        self.stdout.write(f"{created} pro(s) de démonstration créé(s), 3 vérifiés.")
