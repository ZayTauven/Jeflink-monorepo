from django.apps import AppConfig


class PaymentsConfig(AppConfig):
    name = "jeflink.payments"
    label = "payments"
    verbose_name = "Paiements"

    def ready(self) -> None:
        from jeflink.trust.services import register_audit_schema

        from . import checks  # noqa: F401 (enregistre le contrôle des canaux factices)
        from .gateways import check_payment_settings

        check_payment_settings()
        register_audit_schema(
            "payments.channel.saved",
            {"slug": str, "gateway": str, "is_active": bool, "created": bool},
        )
