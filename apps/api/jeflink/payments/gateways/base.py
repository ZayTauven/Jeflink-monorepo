"""Interface des passerelles de paiement (ADR 0002, 0012). Aucun domaine n'appelle un fournisseur
directement : tout passe par ``payments.gateways.get_gateway(name)`` (règle 3).

Une passerelle n'écrit jamais en base : elle dit ce que devient l'intention (``GatewayResult``),
``payments.services`` l'enregistre. Règles pour tout adaptateur : montants en entiers XOF ; ne
jamais journaliser la référence de transaction, le numéro payeur ni un corps HTTP.

V1 : règlements manuels (mobile money déclaré, espèces au bureau). V2 : WiiPay (paiement en
ligne, remboursement, versement, webhook) arrivera comme un adaptateur de plus.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class GatewayResult:
    status: str  # statut de ``PaymentIntent`` après l'opération
    external_ref: str = ""  # référence du fournisseur (V2), jamais une donnée personnelle


class GatewayError(Exception):
    """Échec d'une passerelle. ``code`` est un code court, sans donnée personnelle."""

    def __init__(self, code: str = "") -> None:
        super().__init__(code)
        self.code = code


class GatewayOperationUnsupported(GatewayError):
    """Opération qu'un adaptateur n'offre pas (remboursement d'un règlement manuel…)."""


def check_amount(amount_xof: object) -> int:
    if type(amount_xof) is not int or amount_xof <= 0:
        raise ValueError("montant invalide : entier XOF strictement positif attendu")
    return amount_xof


class PaymentGateway(ABC):
    name: str

    @abstractmethod
    def create_intent(self, *, intent) -> GatewayResult:
        """Ouvre une intention (pas encore enregistrée) : déclaration, encaissement, paiement."""

    @abstractmethod
    def confirm(self, *, intent, received_xof: int) -> GatewayResult:
        """Constate que ``received_xof`` a été reçu pour l'intention."""

    @abstractmethod
    def refund(self, *, intent, amount_xof: int, idempotency_key: str) -> GatewayResult:
        """Rembourse tout ou partie d'une intention confirmée."""

    @abstractmethod
    def payout(self, *, provider, amount_xof: int, idempotency_key: str) -> GatewayResult:
        """Verse ``amount_xof`` à un pro."""

    @abstractmethod
    def verify_webhook(self, request) -> dict[str, Any]:
        """Authentifie un appel du fournisseur et renvoie son contenu utile."""
