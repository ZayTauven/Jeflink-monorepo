import pytest
from django.core.checks import Error
from django.db import IntegrityError, transaction

from jeflink.accounts.deletion import _anonymize
from jeflink.accounts.models import Role
from jeflink.accounts.selectors import has_role
from jeflink.catalog.tests.factories import TradeFactory
from jeflink.common.errors import DomainError
from jeflink.providers import services
from jeflink.providers.checks import demo_providers
from jeflink.providers.models import Provider
from jeflink.trust.models import AuditEvent
from jeflink.zones.tests.factories import ZoneFactory

from .factories import ProviderFactory, VerifiedProviderFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def scope():
    trade = TradeFactory()
    return [trade], [ZoneFactory(trades=[trade])]


def onboard(user, scope, **overrides):
    trades, zones = scope
    args = {
        "user": user,
        "business_name": "Plomberie Ibou",
        "trades": trades,
        "zones": zones,
        "operator": "admin-1",
        **overrides,
    }
    return services.onboard_provider(**args)


def test_onboard_cree_une_fiche_pending_et_le_role_owner(complete_user_factory, scope):
    user = complete_user_factory()
    provider = onboard(user, scope)
    assert provider.status == Provider.Status.PENDING
    assert provider.trades.count() == 1 and provider.zones.count() == 1
    assert has_role(user, Role.OWNER)
    actions = set(AuditEvent.objects.values_list("action", flat=True))
    assert {"accounts.role.granted", "providers.provider.onboarded"} <= actions
    granted = AuditEvent.objects.get(action="accounts.role.granted")
    assert granted.metadata["reason_code"] == "provider_onboarded"


def test_onboard_deux_fois_refuse(complete_user_factory, scope):
    user = complete_user_factory()
    onboard(user, scope)
    with pytest.raises(DomainError) as exc:
        onboard(user, scope)
    assert exc.value.code == "provider_exists"


@pytest.mark.parametrize("name", ["", "A", "x" * 61, "Appelez le 77 123 45 67"])
def test_onboard_nom_invalide(complete_user_factory, scope, name):
    with pytest.raises(DomainError) as exc:
        onboard(complete_user_factory(), scope, business_name=name)
    assert exc.value.code == "business_name_invalid"


def test_onboard_sans_metier_ni_zone(complete_user_factory, scope):
    with pytest.raises(DomainError) as exc:
        onboard(complete_user_factory(), ([], scope[1]))
    assert exc.value.code == "provider_scope_required"


def test_onboard_metier_inactif_refuse(complete_user_factory):
    trade = TradeFactory(is_active=False)
    with pytest.raises(DomainError) as exc:
        onboard(complete_user_factory(), ([trade], [ZoneFactory()]))
    assert exc.value.code == "provider_scope_invalid"


def test_onboard_compte_de_revue_refuse(complete_user_factory, scope):
    user = complete_user_factory(is_review_account=True)
    with pytest.raises(DomainError) as exc:
        onboard(user, scope)
    assert exc.value.code == "role_not_allowed"
    assert not Provider.objects.exists()


def test_pro_de_demo_refuse_hors_local(settings, complete_user_factory, scope):
    settings.DJANGO_ENV = "production"
    with pytest.raises(DomainError) as exc:
        onboard(complete_user_factory(), scope, is_demo=True)
    assert exc.value.code == "demo_forbidden"


def test_controle_au_demarrage_des_pros_de_demo(settings):
    ProviderFactory(is_demo=True)
    assert demo_providers(None, databases={"default"}) == []  # test : permis
    settings.DJANGO_ENV = "production"
    errors = demo_providers(None, databases={"default"})
    assert [e.id for e in errors] == ["providers.E001"]
    assert isinstance(errors[0], Error)


def test_verifier_puis_suspendre_et_retablir(user_factory):
    ops = user_factory()
    provider = ProviderFactory()
    services.set_status(provider=provider, to=Provider.Status.VERIFIED, actor=ops)
    services.set_status(provider=provider, to=Provider.Status.SUSPENDED, actor=ops)
    services.set_status(provider=provider, to=Provider.Status.VERIFIED, actor=ops)
    provider.refresh_from_db()
    assert provider.status == Provider.Status.VERIFIED and provider.status_changed_at
    events = AuditEvent.objects.filter(action="providers.status.changed").order_by("created_at")
    assert [e.metadata["to_status"] for e in events] == ["verified", "suspended", "verified"]
    assert all(e.actor_kind == "ops" and e.actor_id == ops.id for e in events)


@pytest.mark.parametrize(
    ("start", "to"),
    [
        ("pending", "pending"),
        ("verified", "verified"),
        ("verified", "pending"),
        ("suspended", "pending"),
    ],
)
def test_transition_interdite(user_factory, start, to):
    provider = ProviderFactory(status=start)
    with pytest.raises(DomainError) as exc:
        services.set_status(provider=provider, to=to, actor=user_factory())
    assert exc.value.code == "transition_not_allowed"


def test_la_suspension_appelle_les_gestionnaires(user_factory, monkeypatch):
    seen = []
    monkeypatch.setitem(services._SUSPENSION_HANDLERS, "t", lambda p: seen.append(p.pk))
    provider = VerifiedProviderFactory()
    services.set_status(provider=provider, to=Provider.Status.SUSPENDED, actor=user_factory())
    assert seen == [provider.pk]


def test_anonymiseur_remplace_le_nom_et_suspend():
    provider = VerifiedProviderFactory(business_name="Plomberie Ibou")
    _anonymize(provider.owner, reason="user_request")
    provider.refresh_from_db()
    assert provider.business_name == services.DELETED_BUSINESS_NAME
    assert provider.status == Provider.Status.SUSPENDED


def test_une_seule_fiche_par_gerant():
    provider = ProviderFactory()
    with pytest.raises(IntegrityError), transaction.atomic():
        Provider.objects.create(owner=provider.owner, business_name="Autre")
