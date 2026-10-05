"""Passerelle factice : toutes les opérations, aucun réseau. ``local`` et ``test`` seulement
(contrôle au démarrage et à l'appel de ``get_gateway``)."""

from typing import Any, ClassVar

from ..models import PaymentIntent
from .base import GatewayResult, PaymentGateway, check_amount


class FakePaymentGateway(PaymentGateway):
    name = "fake"
    # Opérations reçues, pour les assertions des tests (montants et clés, rien de personnel).
    calls: ClassVar[list[tuple[str, int, str]]] = []

    @classmethod
    def reset(cls) -> None:
        cls.calls.clear()

    def create_intent(self, *, intent) -> GatewayResult:
        check_amount(intent.declared_xof)
        self.calls.append(("create_intent", intent.declared_xof, intent.idempotency_key))
        return GatewayResult(status=PaymentIntent.Status.DECLARED, external_ref="fake")

    def confirm(self, *, intent, received_xof: int) -> GatewayResult:
        check_amount(received_xof)
        self.calls.append(("confirm", received_xof, intent.idempotency_key))
        return GatewayResult(status=PaymentIntent.Status.CONFIRMED, external_ref="fake")

    def refund(self, *, intent, amount_xof: int, idempotency_key: str) -> GatewayResult:
        check_amount(amount_xof)
        self.calls.append(("refund", amount_xof, idempotency_key))
        return GatewayResult(status=PaymentIntent.Status.CONFIRMED, external_ref="fake")

    def payout(self, *, provider, amount_xof: int, idempotency_key: str) -> GatewayResult:
        check_amount(amount_xof)
        self.calls.append(("payout", amount_xof, idempotency_key))
        return GatewayResult(status=PaymentIntent.Status.CONFIRMED, external_ref="fake")

    def verify_webhook(self, request) -> dict[str, Any]:
        self.calls.append(("verify_webhook", 0, ""))
        return {}
