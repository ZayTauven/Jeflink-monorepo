from django.apps import AppConfig


class ZonesConfig(AppConfig):
    name = "jeflink.zones"
    label = "zones"
    verbose_name = "Zones"

    def ready(self) -> None:
        from . import checks  # noqa: F401  (slugs réservés, spec 006)
