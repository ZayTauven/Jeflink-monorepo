from django.apps import AppConfig


class CommonConfig(AppConfig):
    name = "jeflink.common"
    label = "common"

    def ready(self) -> None:
        from .secrets import check_secrets

        check_secrets()
