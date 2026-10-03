from django.apps import AppConfig


class BookingsConfig(AppConfig):
    name = "jeflink.bookings"
    label = "bookings"
    verbose_name = "Réservations"

    def ready(self) -> None:
        from jeflink.accounts.deletion import register_anonymizer, register_deletion_blocker
        from jeflink.providers.services import register_suspension_handler
        from jeflink.trust.services import register_audit_schema

        from .services import (
            anonymize_bookings,
            cancel_for_suspended_provider,
            deletion_blocker,
        )

        register_audit_schema("bookings.booking.created", {"urgent": bool})
        register_audit_schema("bookings.booking.confirmed", {})
        register_audit_schema(
            "bookings.booking.cancelled",
            {
                "from_status": str,
                "cancelled_by": str,
                "reason": str,
                "late": bool,
                "reliability_weight": int,
            },
        )
        register_audit_schema(
            "bookings.booking.progressed", {"from_status": str, "to_status": str, "chained": bool}
        )
        register_audit_schema("bookings.booking.closed", {"reason": str})
        register_audit_schema(
            "bookings.booking.completed", {"completion_method": str, "no_code_reason": str}
        )
        register_audit_schema("bookings.completion_code.failed", {"attempts": int, "locked": bool})
        register_audit_schema("bookings.completion_code.regenerated", {"regenerations": int})
        register_audit_schema("bookings.completion_code.sms", {"automatic": bool, "sent": int})
        register_audit_schema("bookings.photo.uploaded", {"phase": str})
        register_audit_schema("bookings.photo.reported", {"phase": str})
        register_audit_schema("bookings.photos.purged", {"count": int, "reason": str})
        register_audit_schema("bookings.no_show.contested", {})
        register_audit_schema(
            "bookings.no_show.decided", {"decision": str, "reliability_weight": int}
        )
        register_anonymizer("bookings", anonymize_bookings)
        register_deletion_blocker("bookings", deletion_blocker)
        register_suspension_handler("bookings", cancel_for_suspended_provider)
