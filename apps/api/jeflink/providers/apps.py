from django.apps import AppConfig


class ProvidersConfig(AppConfig):
    name = "jeflink.providers"
    label = "providers"
    verbose_name = "Pros"

    def ready(self) -> None:
        from jeflink.accounts.deletion import register_anonymizer
        from jeflink.trust.services import register_audit_schema

        from . import checks  # noqa: F401  (pros de démo hors local/test)
        from .services import anonymize_provider

        register_audit_schema("providers.provider.onboarded", {"operator": str, "demo": bool})
        register_audit_schema(
            "providers.status.changed",
            {"from_status": str, "to_status": str, "reason": str},
        )
        register_anonymizer("providers", anonymize_provider)
