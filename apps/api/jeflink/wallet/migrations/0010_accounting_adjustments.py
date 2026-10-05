"""« Comptabilité » passe les avoirs, gestes commerciaux, corrections et contre-passations
(spec 005, tâche 6), toujours avec un motif, une note et un code TOTP frais."""

from django.contrib.auth.management import create_permissions
from django.db import migrations


def grant(apps, schema_editor):
    app_config = apps.get_app_config("wallet")
    app_config.models_module = True
    create_permissions(app_config, apps=apps, verbosity=0)
    app_config.models_module = None

    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    Group.objects.get(name="Comptabilité").permissions.add(
        Permission.objects.get(content_type__app_label="wallet", codename="adjust_ledger")
    )


class Migration(migrations.Migration):
    dependencies = [("wallet", "0009_adjust_permission")]

    operations = [migrations.RunPython(grant, migrations.RunPython.noop)]
