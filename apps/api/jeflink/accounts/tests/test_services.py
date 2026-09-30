import pytest
from django.utils import timezone

from jeflink.accounts.models import Role, RoleGrant
from jeflink.accounts.selectors import active_roles, has_role
from jeflink.accounts.services import grant_role, revoke_role
from jeflink.common.errors import DomainError
from jeflink.trust.models import AuditEvent


@pytest.mark.django_db
def test_grant_role_audite_et_idempotent(user_factory):
    user = user_factory()
    first = grant_role(user=user, role=Role.OWNER, reason_code="signup")
    second = grant_role(user=user, role=Role.OWNER, reason_code="signup")
    assert first == second
    assert active_roles(user) == {"owner"}
    event = AuditEvent.objects.get(action="accounts.role.granted")
    assert event.actor_kind == "system"
    assert event.target_public_id == user.public_id
    assert event.metadata == {"role": "owner", "reason_code": "signup"}


@pytest.mark.django_db
def test_roles_cumulables(user_factory):
    user = user_factory()
    grant_role(user=user, role=Role.OWNER, reason_code="t")
    grant_role(user=user, role=Role.OPS, reason_code="t", operator="zay", second_operator="awa")
    assert active_roles(user) == {"owner", "ops"}
    assert AuditEvent.objects.filter(actor_kind="ops").count() == 1


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("champs", "code"),
    [
        ({"is_review_account": True}, "role_not_allowed"),
        ({"is_staff": True}, "role_not_allowed"),
        ({"is_superuser": True}, "role_not_allowed"),
        ({"is_active": False, "deactivation_reason": "fraud"}, "account_disabled"),
    ],
)
def test_grant_role_refuse(user_factory, champs, code):
    user = user_factory(**champs)
    with pytest.raises(DomainError) as exc:
        grant_role(user=user, role=Role.OWNER, reason_code="t")
    assert exc.value.code == code
    assert not RoleGrant.objects.exists()


@pytest.mark.django_db
def test_grant_role_lit_l_etat_en_base(user_factory):
    user = user_factory()
    type(user).objects.filter(pk=user.pk).update(is_review_account=True)
    with pytest.raises(DomainError):
        grant_role(user=user, role=Role.OWNER, reason_code="t")  # instance périmée


@pytest.mark.django_db
def test_grant_role_refuse_compte_supprime(user_factory):
    user = user_factory(deleted_at=timezone.now())
    with pytest.raises(DomainError):
        grant_role(user=user, role=Role.OWNER, reason_code="t")


@pytest.mark.django_db
def test_role_inconnu(user_factory):
    with pytest.raises(DomainError) as exc:
        grant_role(user=user_factory(), role="client", reason_code="t")
    assert exc.value.code == "role_unknown"


@pytest.mark.django_db
def test_revoke_role(user_factory):
    user = user_factory()
    grant_role(user=user, role=Role.TECHNICIAN, reason_code="t")
    assert revoke_role(user=user, role=Role.TECHNICIAN, reason_code="left_team") is True
    assert revoke_role(user=user, role=Role.TECHNICIAN, reason_code="left_team") is False
    assert not has_role(user, Role.TECHNICIAN)
    assert AuditEvent.objects.filter(action="accounts.role.revoked").count() == 1
