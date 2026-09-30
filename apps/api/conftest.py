import pytest
from pytest_factoryboy import register

from jeflink.accounts.tests.factories import CompleteUserFactory, RoleGrantFactory, UserFactory

register(UserFactory)
register(CompleteUserFactory)
register(RoleGrantFactory)


@pytest.fixture
def api_client():
    from rest_framework.test import APIClient

    return APIClient()
