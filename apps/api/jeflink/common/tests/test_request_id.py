import pytest
from django.urls import reverse


@pytest.mark.django_db
def test_request_id_genere(client):
    assert len(client.get(reverse("health"))["X-Request-Id"]) == 32


@pytest.mark.django_db
def test_request_id_repris_si_bien_forme(client):
    response = client.get(reverse("health"), HTTP_X_REQUEST_ID="abc-12345678")
    assert response["X-Request-Id"] == "abc-12345678"


@pytest.mark.django_db
def test_request_id_malforme_remplace(client):
    response = client.get(reverse("health"), HTTP_X_REQUEST_ID="<script>")
    assert response["X-Request-Id"] != "<script>"
