from django.apps import AppConfig


class RequestsConfig(AppConfig):
    name = "jeflink.requests"
    label = "requests"
    verbose_name = "Demandes"

    def ready(self) -> None:
        from jeflink.accounts.deletion import register_anonymizer
        from jeflink.trust.services import register_audit_schema

        from .services import anonymize_requests

        register_audit_schema(
            "requests.request.created", {"status": str, "channel": str, "urgent": bool}
        )
        register_audit_schema(
            "requests.request.cancelled", {"from_status": str, "reason": str, "has_note": bool}
        )
        register_audit_schema("requests.request.zone_attached", {"zone_slug": str})
        register_anonymizer("requests", anonymize_requests)
