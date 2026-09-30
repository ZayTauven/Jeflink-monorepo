from django.http import Http404
from rest_framework import exceptions, serializers

from jeflink.common.api.exceptions import exception_handler
from jeflink.common.errors import DomainError


def handle(exc):
    return exception_handler(exc, {})


def test_erreur_metier():
    response = handle(DomainError("otp_rate_limited", status=429, retry_after=120))
    assert response.status_code == 429
    assert response.data == {"code": "otp_rate_limited", "retry_after": 120}


def test_404_uniforme():
    assert handle(Http404()).data == {"code": "not_found"}


def test_validation_sans_echo_de_la_saisie():
    class S(serializers.Serializer):
        public_id = serializers.UUIDField()

    s = S(data={"public_id": "+221771234567"})
    assert not s.is_valid()
    response = handle(exceptions.ValidationError(s.errors))
    assert response.data == {"code": "invalid", "fields": {"public_id": ["invalid"]}}
    assert "771234567" not in str(response.data)


def test_permission_refusee_avec_code():
    response = handle(exceptions.PermissionDenied(code="profile_incomplete"))
    assert response.status_code == 403
    assert response.data == {"code": "profile_incomplete"}


def test_limitation_avec_delai():
    response = handle(exceptions.Throttled(wait=30))
    assert response.data == {"code": "throttled", "retry_after": 30}
