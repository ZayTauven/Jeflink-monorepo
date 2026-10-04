from django.apps import AppConfig


class TrustConfig(AppConfig):
    name = "jeflink.trust"
    label = "trust"
    verbose_name = "Confiance"

    def ready(self) -> None:
        from jeflink.accounts.deletion import register_anonymizer

        from .services import anonymize_disputes

        register_anonymizer("trust", anonymize_disputes)
