import logging.config
import os

from celery import Celery
from celery.signals import setup_logging

# Sans DJANGO_SETTINGS_MODULE explicite, on démarre avec les réglages de production (I1).
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "jeflink.settings.production")

app = Celery("jeflink")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()


@setup_logging.connect
def configure_logging(**kwargs) -> None:
    """Le worker applique LOGGING (et son filtre de données personnelles) au lieu du sien."""
    from django.conf import settings

    logging.config.dictConfig(settings.LOGGING)
