import pytest
from django.contrib.auth.models import Group
from django.urls import reverse

from jeflink.accounts.models import User
from jeflink.providers.models import Provider
from jeflink.trust.models import AuditEvent

from .factories import ProviderFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _second_facteur_valide(monkeypatch):
    monkeypatch.setattr("jeflink.accounts.admin_site.admin_mfa_valid", lambda request: True)


def login(client, group: str | None):
    user = User.objects.create_user("+221770000601", is_staff=True)
    if group:
        user.groups.add(Group.objects.get(name=group))
    client.force_login(user)
    return user


def run_action(client, action: str, *providers):
    return client.post(
        reverse("admin:providers_provider_changelist"),
        {"action": action, "_selected_action": [p.pk for p in providers]},
        follow=True,
    )


def test_le_groupe_verifie_puis_suspend(client):
    ops = login(client, "Validation pros")
    provider = ProviderFactory()
    run_action(client, "verify", provider)
    provider.refresh_from_db()
    assert provider.status == Provider.Status.VERIFIED
    run_action(client, "suspend", provider)
    provider.refresh_from_db()
    assert provider.status == Provider.Status.SUSPENDED
    assert AuditEvent.objects.filter(action="providers.status.changed", actor=ops).count() == 2


def test_saisie_catalogue_ne_peut_pas_verifier(client):
    login(client, "Saisie catalogue")
    provider = ProviderFactory()
    response = client.get(reverse("admin:providers_provider_changelist"))
    assert response.status_code == 403
    run_action(client, "verify", provider)
    provider.refresh_from_db()
    assert provider.status == Provider.Status.PENDING


def test_la_liste_affiche_le_compteur_de_masquages(client):
    login(client, "Validation pros")
    ProviderFactory(masked_numbers_count=7)
    response = client.get(reverse("admin:providers_provider_changelist"))
    assert response.status_code == 200
    assert b"7" in response.content


def test_ni_creation_ni_suppression_dans_l_admin(client):
    login(client, "Validation pros")
    assert client.get(reverse("admin:providers_provider_add")).status_code == 403
