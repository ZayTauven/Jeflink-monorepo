"""Écritures des pros (spec 003) : création par l'Ops, vérification, suspension.

Une suspension a des effets dans d'autres domaines (devis retirés, réservations annulées) :
ils s'enregistrent par ``register_suspension_handler`` et passent par leurs propres services.
"""

import re
from collections.abc import Callable, Iterable

from django.conf import settings
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from jeflink.accounts.models import Role, User
from jeflink.accounts.services import grant_role
from jeflink.catalog.models import Trade
from jeflink.common.errors import DomainError
from jeflink.common.pii import contains_pii
from jeflink.trust.models import AuditEvent
from jeflink.trust.services import audit
from jeflink.zones.models import Zone

from .models import BUSINESS_NAME_MAX_LENGTH, Provider

SuspensionHandler = Callable[[Provider], None]
_SUSPENSION_HANDLERS: dict[str, SuspensionHandler] = {}

# Couples permis ; tout autre couple (ou rester au même statut) est refusé.
_ALLOWED = {
    (Provider.Status.PENDING, Provider.Status.VERIFIED),
    (Provider.Status.PENDING, Provider.Status.SUSPENDED),
    (Provider.Status.VERIFIED, Provider.Status.SUSPENDED),
    (Provider.Status.SUSPENDED, Provider.Status.VERIFIED),
}
DELETED_BUSINESS_NAME = "Pro supprimé"
_SPACES = re.compile(r"\s+")


def register_suspension_handler(domain: str, handler: SuspensionHandler) -> None:
    """Appelé dans le ``ready()`` d'un domaine touché par la suspension d'un pro.

    Le gestionnaire s'exécute dans la transaction du changement de statut, sur la fiche
    verrouillée, et passe par les services de son domaine.
    """
    current = _SUSPENSION_HANDLERS.get(domain)
    if current is not None and current is not handler:
        raise ValueError(f"gestionnaire de suspension déjà enregistré : {domain}")
    _SUSPENSION_HANDLERS[domain] = handler


def clean_business_name(raw: str) -> str:
    name = _SPACES.sub(" ", raw or "").strip()
    if not 2 <= len(name) <= BUSINESS_NAME_MAX_LENGTH or contains_pii(name):
        raise DomainError("business_name_invalid")
    return name


@transaction.atomic
def onboard_provider(
    *,
    user: User,
    business_name: str,
    trades: Iterable[Trade],
    zones: Iterable[Zone],
    operator: str,
    is_demo: bool = False,
) -> Provider:
    """Crée la fiche en ``pending`` et accorde le rôle ``owner`` (motif ``provider_onboarded``).

    L'inscription en libre-service viendra avec l'app Pro (étape 6). ``is_demo`` n'est permis
    qu'en local et en test.
    """
    if is_demo and settings.DJANGO_ENV not in {"local", "test"}:
        raise DomainError("demo_forbidden", status=403)
    name = clean_business_name(business_name)
    trades, zones = list(trades), list(zones)
    if not trades or not zones:
        raise DomainError("provider_scope_required")
    if any(not trade.is_active for trade in trades) or any(not zone.is_active for zone in zones):
        raise DomainError("provider_scope_invalid")
    user = User.objects.select_for_update(no_key=True).get(pk=user.pk)
    if Provider.objects.filter(owner=user).exists():
        raise DomainError("provider_exists", status=409)
    # Refuse les comptes de revue, techniques, désactivés ou supprimés.
    grant_role(user=user, role=Role.OWNER, reason_code="provider_onboarded", operator=operator)
    provider = Provider.objects.create(owner=user, business_name=name, is_demo=is_demo)
    provider.trades.set(trades)
    provider.zones.set(zones)
    audit(
        action="providers.provider.onboarded",
        actor_kind=AuditEvent.ActorKind.OPS,
        target=provider,
        metadata={"operator": operator, "demo": is_demo},
    )
    return provider


def _apply_status(
    provider: Provider, to: str, *, actor: User | None, actor_kind: str, reason: str
) -> Provider:
    """Change le statut d'une fiche déjà verrouillée, journalise, applique les effets."""
    if (provider.status, to) not in _ALLOWED:
        raise DomainError("transition_not_allowed", status=409)
    previous = provider.status
    provider.status = to
    provider.status_changed_at = timezone.now()
    provider.save(update_fields=["status", "status_changed_at", "updated_at"])
    audit(
        action="providers.status.changed",
        actor=actor,
        actor_kind=actor_kind,
        target=provider,
        metadata={"from_status": previous, "to_status": to, "reason": reason},
    )
    if to == Provider.Status.SUSPENDED:
        for handler in _SUSPENSION_HANDLERS.values():
            handler(provider)
    return provider


@transaction.atomic
def set_status(
    *, provider: Provider, to: str, actor: User | None, reason: str = "admin_action"
) -> Provider:
    """Vérifie, suspend ou rétablit un pro (actions d'admin, groupe « Validation pros »).

    Sans ``actor`` (commande de démonstration), l'événement est écrit au nom du système.
    """
    provider = Provider.objects.select_for_update().get(pk=provider.pk)
    kind = AuditEvent.ActorKind.OPS if actor else AuditEvent.ActorKind.SYSTEM
    return _apply_status(provider, to, actor=actor, actor_kind=kind, reason=reason)


@transaction.atomic
def anonymize_provider(user: User) -> None:
    """Anonymiseur : le nom commercial est remplacé et la fiche suspendue (effets compris)."""
    for provider in Provider.objects.select_for_update().filter(owner=user):
        provider.business_name = DELETED_BUSINESS_NAME
        provider.save(update_fields=["business_name", "updated_at"])
        if provider.status != Provider.Status.SUSPENDED:
            _apply_status(
                provider,
                Provider.Status.SUSPENDED,
                actor=None,
                actor_kind=AuditEvent.ActorKind.SYSTEM,
                reason="account_deleted",
            )
        else:
            for handler in _SUSPENSION_HANDLERS.values():
                handler(provider)


def count_masked_numbers(*, provider: Provider, count: int) -> None:
    """Incrémente le compteur de masquages d'un pro (jamais le texte masqué)."""
    if count > 0:
        Provider.objects.filter(pk=provider.pk).update(
            masked_numbers_count=F("masked_numbers_count") + count, updated_at=timezone.now()
        )
