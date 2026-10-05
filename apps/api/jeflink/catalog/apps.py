from django.apps import AppConfig


class CatalogConfig(AppConfig):
    name = "jeflink.catalog"
    label = "catalog"
    verbose_name = "Catalogue"

    def ready(self) -> None:
        from . import checks  # noqa: F401  (slugs réservés, spec 006)
