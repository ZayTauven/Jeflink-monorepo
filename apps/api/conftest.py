import pytest
from pytest_factoryboy import register

from jeflink.accounts.tests.factories import CompleteUserFactory, RoleGrantFactory, UserFactory

register(UserFactory)
register(CompleteUserFactory)
register(RoleGrantFactory)


@pytest.fixture(autouse=True)
def _isolation_redis_et_sms():
    """Chaque test part de compteurs vides et d'une boîte d'envoi SMS vide."""
    from jeflink.common.ratelimit import client
    from jeflink.notifications.sms.fake import FakeSmsGateway

    client().flushdb()
    FakeSmsGateway.reset()
    yield
    FakeSmsGateway.reset()


@pytest.fixture
def redis_down(settings):
    """Simule un Redis de limitation injoignable."""
    settings.RATELIMIT_REDIS_URL = "redis://127.0.0.1:1/0"


@pytest.fixture
def api_client():
    from rest_framework.test import APIClient

    return APIClient()


@pytest.fixture(autouse=True)
def _stockage_photos_vide():
    """Chaque test part d'un stockage d'objets vide (``InMemoryStorage``, aucun réseau)."""
    from django.core.files.storage import storages
    from django.core.files.storage.memory import InMemoryDirNode

    storages["photos"]._root = InMemoryDirNode()
    yield
