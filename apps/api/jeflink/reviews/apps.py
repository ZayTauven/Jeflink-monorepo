from django.apps import AppConfig


class ReviewsConfig(AppConfig):
    name = "jeflink.reviews"
    label = "reviews"
    verbose_name = "Avis"

    def ready(self) -> None:
        from jeflink.accounts.deletion import register_anonymizer
        from jeflink.bookings.services import register_close_handler
        from jeflink.trust.services import register_audit_schema

        from .services import anonymize_reviews, publish_on_close

        register_audit_schema("reviews.review.submitted", {"rating": int, "edited": bool})
        register_audit_schema("reviews.review.hidden", {"reason": str})
        register_audit_schema("reviews.review.restored", {})
        register_close_handler(publish_on_close)
        register_anonymizer("reviews", anonymize_reviews)
