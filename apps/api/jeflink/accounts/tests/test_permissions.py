import time
from datetime import timedelta

import pytest
from django.contrib.auth.models import AnonymousUser, Group
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory

from jeflink.accounts.models import Role
from jeflink.accounts.permissions import (
    HasOpsPerm,
    HasOwnerRole,
    HasTechnicianRole,
    IsClient,
    IsProOwner,
    IsTechnicianAssigned,
    RequiresCompleteProfile,
    RequiresRecentAuth,
)
from jeflink.accounts.services import grant_role


def make_request(user, claims=None):
    request = Request(APIRequestFactory().get("/"))
    request.user = user
    request.auth = claims or {}
    return request


def allowed(permission_class, request):
    return permission_class().has_permission(request, view=None)


@pytest.fixture
def ops_user(user_factory):
    user = user_factory()
    grant_role(user=user, role=Role.OPS, reason_code="t", operator="a", second_operator="b")
    user.groups.add(Group.objects.get(name="Support"))
    return user


@pytest.mark.django_db
def test_is_client(user_factory):
    assert allowed(IsClient, make_request(user_factory()))
    assert not allowed(IsClient, make_request(AnonymousUser()))
    assert not allowed(
        IsClient, make_request(user_factory(is_active=False, deactivation_reason="ops_other"))
    )


@pytest.mark.django_db
def test_comptes_techniques_refuses_par_l_api(user_factory):
    assert not allowed(IsClient, make_request(user_factory(is_staff=True)))
    assert not allowed(IsClient, make_request(user_factory(is_superuser=True)))


@pytest.mark.django_db
def test_profil_complet_exige(user_factory, complete_user_factory):
    assert not allowed(RequiresCompleteProfile, make_request(user_factory()))
    assert allowed(RequiresCompleteProfile, make_request(complete_user_factory()))
    assert RequiresCompleteProfile.code == "profile_incomplete"


@pytest.mark.django_db
def test_authentification_recente(user_factory):
    perm = RequiresRecentAuth(timedelta(minutes=5))
    user = user_factory()
    assert allowed(perm, make_request(user, {"auth_time": int(time.time()) - 60}))
    assert not allowed(perm, make_request(user, {"auth_time": int(time.time()) - 600}))
    assert not allowed(perm, make_request(user, {}))
    assert not allowed(perm, make_request(user, {"auth_time": True}))
    # Horodatage dans le futur ou aberrant : refusé, sans erreur 500.
    assert not allowed(perm, make_request(user, {"auth_time": int(time.time()) + 3600}))
    assert not allowed(perm, make_request(user, {"auth_time": 10**20}))


@pytest.mark.django_db
def test_roles_pro(user_factory):
    solo, tech, client = user_factory(), user_factory(), user_factory()
    grant_role(user=solo, role=Role.OWNER, reason_code="t")
    grant_role(user=tech, role=Role.TECHNICIAN, reason_code="t")
    assert allowed(HasOwnerRole, make_request(solo))
    assert not allowed(HasOwnerRole, make_request(tech))
    # L'artisan solo est son propre technicien (ADR 0003).
    assert allowed(HasTechnicianRole, make_request(solo))
    assert allowed(HasTechnicianRole, make_request(tech))
    assert not allowed(HasTechnicianRole, make_request(client))


@pytest.mark.django_db
def test_ops_view_exige_role_mfa_et_groupe(ops_user, user_factory):
    view = HasOpsPerm("ops.accounts.view", step_up=False)
    assert allowed(view, make_request(ops_user, {"mfa": True}))
    assert not allowed(view, make_request(ops_user, {"mfa": False}))
    assert not allowed(view, make_request(ops_user, {}))
    sans_role = user_factory()
    sans_role.groups.add(Group.objects.get(name="Support"))
    assert not allowed(view, make_request(sans_role, {"mfa": True}))


@pytest.mark.django_db
def test_ops_manage_exige_step_up(ops_user):
    manage = HasOpsPerm("ops.accounts.manage", step_up=True)
    now = int(time.time())
    assert allowed(manage, make_request(ops_user, {"mfa": True, "mfa_at": now - 60}))
    permission = manage()
    request = make_request(ops_user, {"mfa": True, "mfa_at": now - 600})
    assert not permission.has_permission(request, view=None)
    assert permission.code == "ops_step_up_required"


@pytest.mark.django_db
def test_ops_change_phone_reserve_admin(ops_user):
    change = HasOpsPerm("ops.accounts.change_phone", step_up=True)
    claims = {"mfa": True, "mfa_at": int(time.time())}
    assert not allowed(change, make_request(ops_user, claims))
    ops_user.groups.add(Group.objects.get(name="Admin"))
    assert allowed(change, make_request(ops_user, claims))


@pytest.mark.django_db
def test_superuser_refuse_meme_avec_role_et_groupe(user_factory):
    root = user_factory(is_superuser=True, is_staff=True)
    root.groups.add(Group.objects.get(name="Admin"))
    assert root.has_perm("accounts.ops_accounts_view")  # vrai pour Django…
    view = HasOpsPerm("ops.accounts.view", step_up=False)
    assert not allowed(view, make_request(root, {"mfa": True}))


@pytest.mark.django_db
def test_classes_objet_refusent_par_defaut(user_factory):
    request = make_request(user_factory())
    for cls in (IsProOwner, IsTechnicianAssigned):
        assert not cls().has_permission(request, None)
        assert not cls().has_object_permission(request, None, object())


def test_permission_ops_mal_nommee():
    with pytest.raises(ValueError):
        HasOpsPerm("accounts.view", step_up=False)
