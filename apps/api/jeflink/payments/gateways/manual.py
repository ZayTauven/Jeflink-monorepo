"""Règlements manuels de la V1 (spec 005) : rien ne part vers un fournisseur.

- ``manual_mobile_money`` : le pro paie vers le numéro marchand Jeflink et déclare la transaction
  (ou l'Ops la relève dans le relevé) ; l'Ops confirme après rapprochement.
- ``cash`` : espèces remises au bureau, saisies par l'Ops avec un numéro de reçu.

Ni remboursement, ni versement, ni webhook : ``GatewayOperationUnsupported``.
"""

from ..models import PaymentIntent
from .base import GatewayOperationUnsupported, GatewayResult, PaymentGateway, check_amount


class _ManualGateway(PaymentGateway):
    def confirm(self, *, intent, received_xof: int) -> GatewayResult:
        check_amount(received_xof)
        if intent.status not in PaymentIntent.PENDING_STATUSES:
            raise ValueError("seule une intention en attente se confirme")
        return GatewayResult(status=PaymentIntent.Status.CONFIRMED)

    def refund(self, *, intent, amount_xof: int, idempotency_key: str) -> GatewayResult:
        raise GatewayOperationUnsupported("refund_unsupported")

    def payout(self, *, provider, amount_xof: int, idempotency_key: str) -> GatewayResult:
        raise GatewayOperationUnsupported("payout_unsupported")

    def verify_webhook(self, request) -> dict:
        raise GatewayOperationUnsupported("webhook_unsupported")


class ManualMobileMoneyGateway(_ManualGateway):
    name = "manual_mobile_money"

    def create_intent(self, *, intent) -> GatewayResult:
        check_amount(intent.declared_xof)
        if not intent.reference:
            raise ValueError("un règlement mobile money porte la référence de sa transaction")
        return GatewayResult(status=PaymentIntent.Status.DECLARED)


class CashGateway(_ManualGateway):
    name = "cash"

    def create_intent(self, *, intent) -> GatewayResult:
        check_amount(intent.declared_xof)
        if not intent.receipt_number or intent.reference:
            raise ValueError("des espèces portent un numéro de reçu, jamais une référence")
        return GatewayResult(status=PaymentIntent.Status.DECLARED)
