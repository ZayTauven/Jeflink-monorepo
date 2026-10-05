"""Point d'entrée unique : ``get_gateway(name)`` renvoie l'adaptateur d'un canal de règlement.

En V1, chaque canal (``SettlementChannel.gateway``) porte sa passerelle. ``PAYMENT_GATEWAY`` est
celle des paiements en ligne (V2) ; elle est vérifiée au démarrage comme les autres.
"""

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from .base import (
    GatewayError,
    GatewayOperationUnsupported,
    GatewayResult,
    PaymentGateway,
)

__all__ = [
    "GatewayError",
    "GatewayOperationUnsupported",
    "GatewayResult",
    "PaymentGateway",
    "check_payment_settings",
    "get_gateway",
]

FAKE_ALLOWED_ENVS = frozenset({"local", "test"})


def _registry() -> dict[str, type[PaymentGateway]]:
    from .fake import FakePaymentGateway
    from .manual import CashGateway, ManualMobileMoneyGateway

    # WiiPay s'ajoute ici (V2).
    return {
        "manual_mobile_money": ManualMobileMoneyGateway,
        "cash": CashGateway,
        "fake": FakePaymentGateway,
    }


def _refuse_fake(name: str) -> None:
    if name == "fake" and settings.DJANGO_ENV not in FAKE_ALLOWED_ENVS:
        raise ImproperlyConfigured(
            f"Passerelle fake interdite avec DJANGO_ENV={settings.DJANGO_ENV}."
        )


def check_payment_settings() -> None:
    """Appelée au démarrage : ``PAYMENT_GATEWAY`` connue, et jamais ``fake`` hors local/test."""
    name = settings.PAYMENT_GATEWAY
    _refuse_fake(name)
    if name not in _registry():
        raise ImproperlyConfigured(f"PAYMENT_GATEWAY inconnu : {name}.")


def get_gateway(name: str) -> PaymentGateway:
    _refuse_fake(name)
    try:
        return _registry()[name]()
    except KeyError:
        raise ImproperlyConfigured(f"Passerelle de paiement inconnue : {name}.") from None
