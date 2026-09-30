from io import StringIO

import pytest
from django.core.management import CommandError, call_command

from jeflink.accounts.selectors import has_role
from jeflink.trust.models import AuditEvent

ARGS = ["--operator", "zay", "--second-operator", "awa", "--reason", "hiring"]


def run(name, *args):
    out = StringIO()
    call_command(name, *args, stdout=out)
    return out.getvalue()


@pytest.mark.django_db
def test_grant_puis_revoke_ops(user_factory):
    user = user_factory(phone="+221771234567")
    out = run("grant_ops_role", "--phone", "77 123 45 67", "--groups", "Support,Admin", *ARGS)
    assert "771234567" not in out  # numéro masqué dans la sortie
    assert has_role(user, "ops")
    assert set(user.groups.values_list("name", flat=True)) == {"Support", "Admin"}
    event = AuditEvent.objects.get(action="accounts.role.granted")
    assert event.metadata == {
        "role": "ops",
        "reason_code": "hiring",
        "operator": "zay",
        "second_operator": "awa",
    }

    run("revoke_ops_role", "--phone", "771234567", *ARGS)
    assert not has_role(user, "ops")
    assert not user.groups.exists()


@pytest.mark.django_db
def test_deux_operateurs_distincts_exiges(user_factory):
    user_factory(phone="+221771234567")
    with pytest.raises(CommandError, match="distinct"):
        run(
            "grant_ops_role",
            "--phone",
            "771234567",
            "--groups",
            "Support",
            "--operator",
            "zay",
            "--second-operator",
            "ZAY",
            "--reason",
            "x",
        )


@pytest.mark.django_db
def test_compte_inexistant_refuse():
    with pytest.raises(CommandError, match="Aucun compte"):
        run("grant_ops_role", "--phone", "771234567", "--groups", "Support", *ARGS)


@pytest.mark.django_db
def test_groupe_inconnu_refuse(user_factory):
    user_factory(phone="+221771234567")
    with pytest.raises(CommandError, match="Groupes"):
        run("grant_ops_role", "--phone", "771234567", "--groups", "Root", *ARGS)
