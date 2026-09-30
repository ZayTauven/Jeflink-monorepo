import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone

from jeflink.accounts.models import Role, RoleGrant, User


@pytest.mark.django_db
def test_create_user_normalise_et_mot_de_passe_inutilisable():
    user = User.objects.create_user("77 123 45 67")
    assert user.phone == "+221771234567"
    assert not user.has_usable_password()
    assert user.profile_status == "guest"
    assert user.preferred_language == "fr"


@pytest.mark.django_db
def test_numero_unique(user_factory):
    user_factory(phone="+221771234567")
    with pytest.raises(IntegrityError):
        user_factory(phone="+221771234567")


@pytest.mark.django_db
@pytest.mark.parametrize(
    "champs",
    [
        {"phone": "771234567"},  # pas en E.164
        {"phone": None},  # ni numéro ni suppression
        {"profile_status": "complete", "display_name": ""},
        {"is_active": False},  # désactivation sans motif
    ],
)
def test_contraintes_en_base(user_factory, champs):
    with pytest.raises(IntegrityError), transaction.atomic():
        user = user_factory()
        User.objects.filter(pk=user.pk).update(**champs)


@pytest.mark.django_db
def test_compte_supprime_sans_numero(user_factory):
    user = user_factory()
    User.objects.filter(pk=user.pk).update(phone=None, deleted_at=timezone.now())


@pytest.mark.django_db
def test_un_seul_role_actif_par_type(user_factory):
    user = user_factory()
    RoleGrant.objects.create(user=user, role=Role.OWNER, reason_code="t")
    with pytest.raises(IntegrityError), transaction.atomic():
        RoleGrant.objects.create(user=user, role=Role.OWNER, reason_code="t")
    RoleGrant.objects.filter(user=user).update(revoked_at=timezone.now())
    RoleGrant.objects.create(user=user, role=Role.OWNER, reason_code="t")


@pytest.mark.django_db
def test_groupes_ops_crees_avec_permissions():
    from django.contrib.auth.models import Group

    admin = Group.objects.get(name="Admin")
    support = Group.objects.get(name="Support")
    assert admin.permissions.filter(codename="ops_accounts_change_phone").exists()
    assert not support.permissions.filter(codename="ops_accounts_change_phone").exists()
    assert set(Group.objects.values_list("name", flat=True)) >= {
        "Support",
        "Validation KYC",
        "Finance",
        "Admin",
    }


@pytest.mark.django_db
def test_groupes_en_lecture_seule_dans_l_admin(rf):
    from django.contrib import admin
    from django.contrib.auth.models import Group

    group_admin = admin.site._registry[Group]
    request = rf.get("/")
    assert not group_admin.has_add_permission(request)
    assert not group_admin.has_change_permission(request)
    assert not group_admin.has_delete_permission(request)
