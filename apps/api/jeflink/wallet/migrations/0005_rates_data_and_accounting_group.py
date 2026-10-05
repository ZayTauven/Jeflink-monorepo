"""Taux de commission (spec 005, tâche 2).

- Immuabilité : comme le grand livre, un taux ne se modifie ni ne se supprime (ajout seul).
- Taux par défaut : 10 % (1 000 points de base), plafond 20 000 F par mission (Q1, Q2). Sa date
  d'effet est antérieure à tout devis, pour que chaque mission ait un taux. Les taux de lancement
  par métier sont chargés par ``seed_reference_data``, comme les métiers.
- Groupe « Comptabilité » : lire le grand livre, ajouter des taux. Les tâches suivantes lui
  ajoutent canaux, avoirs, corrections et contre-passations.
"""

from datetime import UTC, datetime

from django.contrib.auth.management import create_permissions
from django.db import migrations
from django.utils import timezone

IMMUTABLE = """
CREATE TRIGGER wallet_commissionrate_immutable
BEFORE UPDATE OR DELETE ON wallet_commissionrate
FOR EACH ROW EXECUTE FUNCTION wallet_ledger_immutable();
"""
IMMUTABLE_BACKWARD = (
    "DROP TRIGGER IF EXISTS wallet_commissionrate_immutable ON wallet_commissionrate;"
)

DEFAULT_RATE = {
    "rate_bps": 1_000,
    "cap_xof": 20_000,
    "valid_from": datetime(2026, 1, 1, tzinfo=UTC),
    "note": "Taux par défaut de lancement (spec 005)",
}

GROUP_NAME = "Comptabilité"
CODENAMES = (
    "view_ledgeraccount",
    "view_ledgertransaction",
    "view_ledgerentry",
    "view_commissionrate",
    "add_commissionrate",
)


def create_default_rate(apps, schema_editor):
    CommissionRate = apps.get_model("wallet", "CommissionRate")
    if CommissionRate.objects.filter(trade__isnull=True).exists():
        return
    rate = CommissionRate.objects.create(trade=None, **DEFAULT_RATE)
    # Horodatage à la milliseconde, comme le sérialiseur JSON de Django : le rechargement des
    # données (``serialized_rollback``) réécrit alors la ligne à l'identique, ce que le trigger
    # d'immuabilité accepte. Fait avant de poser le trigger.
    now = timezone.now()
    stamp = now.replace(microsecond=now.microsecond - now.microsecond % 1000)
    CommissionRate.objects.filter(pk=rate.pk).update(created_at=stamp, updated_at=stamp)


def create_group(apps, schema_editor):
    app_config = apps.get_app_config("wallet")
    app_config.models_module = True
    create_permissions(app_config, apps=apps, verbosity=0)
    app_config.models_module = None

    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    group, _ = Group.objects.get_or_create(name=GROUP_NAME)
    group.permissions.add(
        *Permission.objects.filter(content_type__app_label="wallet", codename__in=CODENAMES)
    )


def delete_group(apps, schema_editor):
    apps.get_model("auth", "Group").objects.filter(name=GROUP_NAME).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("wallet", "0004_commission_rate"),
        ("auth", "0012_alter_user_first_name_max_length"),
        ("contenttypes", "0002_remove_content_type_name"),
    ]

    operations = [
        migrations.RunPython(create_default_rate, migrations.RunPython.noop),
        migrations.RunSQL(IMMUTABLE, IMMUTABLE_BACKWARD),
        migrations.RunPython(create_group, delete_group),
    ]
