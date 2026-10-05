"""« Comptabilité » gère les canaux de règlement (ajout, modification, jamais de suppression) et
consulte les intentions de paiement (spec 005, tâche 4)."""

from django.contrib.auth.management import create_permissions
from django.db import migrations

CODENAMES = (
    "view_settlementchannel",
    "add_settlementchannel",
    "change_settlementchannel",
    "view_paymentintent",
)


def grant(apps, schema_editor):
    app_config = apps.get_app_config("payments")
    app_config.models_module = True
    create_permissions(app_config, apps=apps, verbosity=0)
    app_config.models_module = None

    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    group = Group.objects.get(name="Comptabilité")
    group.permissions.add(
        *Permission.objects.filter(content_type__app_label="payments", codename__in=CODENAMES)
    )


class Migration(migrations.Migration):
    dependencies = [
        ("payments", "0001_initial"),
        ("wallet", "0005_rates_data_and_accounting_group"),
    ]

    operations = [migrations.RunPython(grant, migrations.RunPython.noop)]
