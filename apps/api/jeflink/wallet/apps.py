from django.apps import AppConfig


class WalletConfig(AppConfig):
    name = "jeflink.wallet"
    label = "wallet"
    verbose_name = "Portefeuille"

    def ready(self) -> None:
        from jeflink.trust.services import register_audit_schema

        register_audit_schema(
            "wallet.rate.added",
            {"trade": str, "rate_bps": int, "cap_xof": (int, type(None)), "immediate": bool},
        )
