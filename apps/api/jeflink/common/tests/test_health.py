import pytest
from django.urls import reverse


@pytest.mark.django_db
def test_health_ok_sans_authentification(client):
    response = client.get(reverse("health"))

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.django_db
def test_postgis_disponible():
    from django.db import connection

    with connection.cursor() as cursor:
        cursor.execute("SELECT PostGIS_Version()")
        assert cursor.fetchone()[0]


@pytest.mark.django_db
def test_schema_openapi_genere(client):
    response = client.get(reverse("schema"))

    assert response.status_code == 200
    assert b"/api/health/" in response.content
