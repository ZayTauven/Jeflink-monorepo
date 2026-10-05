from django.apps import AppConfig


class PaymentsConfig(AppConfig):
    name = "jeflink.payments"
    label = "payments"
    verbose_name = "Paiements"

    def ready(self) -> None:
        from jeflink.trust.services import register_audit_schema
        from jeflink.wallet.selectors import register_pending_source

        from . import checks  # noqa: F401 (enregistre le contrôle des canaux factices)
        from .gateways import check_payment_settings
        from .services import counted_pending_xof

        check_payment_settings()
        register_audit_schema(
            "payments.channel.saved",
            {"slug": str, "gateway": str, "is_active": bool, "created": bool},
        )
        # Montants et codes seulement : jamais la référence ni les chiffres du payeur.
        register_audit_schema("payments.settlement.declared", {"amount_xof": int, "channel": str})
        register_audit_schema("payments.settlement.cancelled", {"amount_xof": int})
        register_audit_schema("payments.settlement.corrected", {"amount_xof": int})
        register_audit_schema(
            "payments.settlement.confirmed",
            {
                "declared_xof": int,
                "received_xof": int,
                "difference_xof": int,
                "channel": str,
                "origin": str,
            },
        )
        register_audit_schema("payments.settlement.correction_requested", {"reason": str})
        register_audit_schema("payments.settlement.rejected", {"reason": str, "declared_xof": int})
        register_audit_schema(
            "payments.settlement.recorded",
            {"amount_xof": int, "channel": str, "gateway": str},
        )
        register_pending_source(counted_pending_xof)
