import pytest
from django.conf import settings
from django.urls import reverse


@pytest.mark.django_db
def test_request_id_genere(client):
    assert len(client.get(reverse("health"))["X-Request-Id"]) == 32


@pytest.mark.django_db
def test_request_id_client_ignore_sans_bff(client):
    response = client.get(reverse("health"), HTTP_X_REQUEST_ID="abc-12345678")
    assert response["X-Request-Id"] != "abc-12345678"


@pytest.mark.django_db
def test_request_id_repris_depuis_le_bff(client):
    response = client.get(
        reverse("health"),
        HTTP_X_REQUEST_ID="abc-12345678",
        HTTP_X_JEFLINK_BFF=settings.BFF_SHARED_SECRETS[0],
    )
    assert response["X-Request-Id"] == "abc-12345678"


@pytest.mark.django_db
def test_request_id_malforme_remplace_meme_depuis_le_bff(client):
    response = client.get(
        reverse("health"),
        HTTP_X_REQUEST_ID="<script>",
        HTTP_X_JEFLINK_BFF=settings.BFF_SHARED_SECRETS[0],
    )
    assert response["X-Request-Id"] != "<script>"
