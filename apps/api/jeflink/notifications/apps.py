from django.apps import AppConfig


class NotificationsConfig(AppConfig):
    name = "jeflink.notifications"
    label = "notifications"
    verbose_name = "Notifications"

    def ready(self) -> None:
        from .sms import check_sms_settings

        check_sms_settings()
