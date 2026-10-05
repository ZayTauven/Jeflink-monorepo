from django.apps import AppConfig


class WalletConfig(AppConfig):
    name = "jeflink.wallet"
    label = "wallet"
    verbose_name = "Portefeuille"

    def ready(self) -> None:
        from jeflink.bookings.services import register_close_handler
        from jeflink.trust.services import register_audit_schema

        from .services import charge_commission_on_close

        register_audit_schema(
            "wallet.rate.added",
            {"trade": str, "rate_bps": int, "cap_xof": (int, type(None)), "immediate": bool},
        )
        register_audit_schema(
            "wallet.commission.recorded",
            {
                "status": str,
                "exempt_reason": str,
                "amount_xof": int,
                "rate_bps": (int, type(None)),
                "completion_method": str,
                "close_reason": str,
            },
        )
        register_close_handler(charge_commission_on_close)
