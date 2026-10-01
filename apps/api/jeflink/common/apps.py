from django.apps import AppConfig


class CommonConfig(AppConfig):
    name = "jeflink.common"
    label = "common"

    def ready(self) -> None:
        from . import checks  # noqa: F401  (contrôles de déploiement, infra 2)
        from .secrets import check_secrets

        check_secrets()
