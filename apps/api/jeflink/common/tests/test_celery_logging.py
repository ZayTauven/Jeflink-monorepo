import logging

from jeflink.celery import configure_logging
from jeflink.common.log_filters import PiiRedactingFilter


def test_le_worker_garde_le_filtre(settings):
    assert settings.CELERY_WORKER_HIJACK_ROOT_LOGGER is False
    configure_logging()
    handlers = logging.getLogger().handlers
    assert handlers
    assert all(any(isinstance(f, PiiRedactingFilter) for f in h.filters) for h in handlers)
