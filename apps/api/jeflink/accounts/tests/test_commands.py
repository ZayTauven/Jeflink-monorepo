from io import StringIO

import pytest
from django.core.management import CommandError, call_command

from jeflink.accounts.selectors import has_role
from jeflink.trust.models import AuditEvent


def run(name, *args):
    out = StringIO()
    call_command(name, *args, stdout=out)
    return out.getvalue()


def bootstrap(user):
    return run(
        "grant_ops_role",
        "--user",
        str(user.public_id),
        "--groups",
        "Admin",
        "--operator",
        "zay",
        "--second-operator",
        "awa",
        "--reason",
        "bootstrap",
        "--bootstrap",
    )


@pytest.fixture
def admins(user_factory):
    """Deux Admin réels. Le bootstrap n'est permis que sans Admin actif : on crée le premier,
    on le sort du groupe le temps de créer le second, puis on l'y remet."""
    from django.contrib.auth.models import Group

    first, second = user_factory(), user_factory()
    bootstrap(first)
    first.groups.clear()
    bootstrap(second)
    first.groups.add(Group.objects.get(name="Admin"))
    return first, second


def ops_args(admins, reason="hiring"):
    return [
        "--operator",
        str(admins[0].public_id),
        "--second-operator",
        str(admins[1].public_id),
        "--reason",
        reason,
    ]


@pytest.mark.django_db
def test_bootstrap_cree_le_premier_admin_puis_se_ferme(user_factory):
    first = user_factory()
    bootstrap(first)
    assert has_role(first, "ops")
    event = AuditEvent.objects.get(action="accounts.ops_groups.changed")
    assert event.metadata["bootstrap"] is True
    assert event.metadata["groups_added"] == ["Admin"]
    with pytest.raises(CommandError, match="Admin existe déjà"):
        bootstrap(user_factory())


@pytest.mark.django_db
def test_grant_puis_revoke_par_deux_admins(admins, user_factory):
    target = user_factory(phone="+221771234567")
    out = run("grant_ops_role", "--phone", "77 123 45 67", "--groups", "Support", *ops_args(admins))
    assert "771234567" not in out  # numéro masqué dans la sortie
    assert has_role(target, "ops")
    changed = AuditEvent.objects.filter(
        action="accounts.ops_groups.changed", target_public_id=target.public_id
    ).get()
    assert changed.metadata == {
        "groups_added": ["Support"],
        "groups_removed": [],
        "operator": str(admins[0].public_id),
        "second_operator": str(admins[1].public_id),
        "reason_code": "hiring",
        "bootstrap": False,
    }

    run("revoke_ops_role", "--user", str(target.public_id), *ops_args(admins, "departure"))
    assert not has_role(target, "ops")
    assert not target.groups.exists()
    removed = (
        AuditEvent.objects.filter(
            action="accounts.ops_groups.changed", target_public_id=target.public_id
        )
        .exclude(pk=changed.pk)
        .get()
    )
    assert removed.metadata["groups_removed"] == ["Support"]


@pytest.mark.django_db
def test_ajout_de_groupe_sur_ops_existant_audite(admins, user_factory):
    target = user_factory()
    run("grant_ops_role", "--user", str(target.public_id), "--groups", "Support", *ops_args(admins))
    run("grant_ops_role", "--user", str(target.public_id), "--groups", "Admin", *ops_args(admins))
    events = AuditEvent.objects.filter(
        action="accounts.ops_groups.changed", target_public_id=target.public_id
    )
    assert sorted(e.metadata["groups_added"][0] for e in events) == ["Admin", "Support"]


@pytest.mark.django_db
def test_operateurs_non_admin_refuses(admins, user_factory):
    target, intrus = user_factory(), user_factory()
    with pytest.raises(CommandError, match="Admin actif"):
        run(
            "grant_ops_role",
            "--user",
            str(target.public_id),
            "--groups",
            "Support",
            "--operator",
            str(admins[0].public_id),
            "--second-operator",
            str(intrus.public_id),
            "--reason",
            "hiring",
        )


@pytest.mark.django_db
def test_operateurs_distincts_et_differents_de_la_cible(admins):
    same = ["--operator", str(admins[0].public_id), "--second-operator", str(admins[0].public_id)]
    with pytest.raises(CommandError, match="distincts"):
        run("revoke_ops_role", "--user", str(admins[1].public_id), *same, "--reason", "departure")
    with pytest.raises(CommandError, match="propre compte"):
        run("revoke_ops_role", "--user", str(admins[0].public_id), *ops_args(admins, "departure"))


@pytest.mark.django_db
def test_operateur_nomme_refuse_hors_bootstrap(admins, user_factory):
    with pytest.raises(CommandError, match="public_id"):
        run(
            "grant_ops_role",
            "--user",
            str(user_factory().public_id),
            "--groups",
            "Support",
            "--operator",
            "zay",
            "--second-operator",
            "awa",
            "--reason",
            "hiring",
        )


@pytest.mark.django_db
def test_motif_hors_liste_refuse(admins, user_factory):
    with pytest.raises(CommandError):
        run(
            "grant_ops_role",
            "--user",
            str(user_factory().public_id),
            "--groups",
            "Support",
            *ops_args(admins, "parce que"),
        )


@pytest.mark.django_db
def test_compte_inexistant_refuse(admins):
    with pytest.raises(CommandError, match="Aucun compte"):
        run("grant_ops_role", "--phone", "771234567", "--groups", "Support", *ops_args(admins))


@pytest.mark.django_db
def test_groupe_inconnu_refuse(admins, user_factory):
    with pytest.raises(CommandError, match="Groupes"):
        run(
            "grant_ops_role",
            "--user",
            str(user_factory().public_id),
            "--groups",
            "Root",
            *ops_args(admins),
        )
