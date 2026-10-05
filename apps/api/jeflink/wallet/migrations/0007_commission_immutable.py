"""Commission immuable jusqu'en base (spec 005, tâche 3) ; « Comptabilité » la consulte."""

from django.contrib.auth.management import create_permissions
from django.db import migrations

FORWARD = """
CREATE TRIGGER wallet_commission_immutable
BEFORE UPDATE OR DELETE ON wallet_commission
FOR EACH ROW EXECUTE FUNCTION wallet_ledger_immutable();
"""
BACKWARD = "DROP TRIGGER IF EXISTS wallet_commission_immutable ON wallet_commission;"


def grant_view(apps, schema_editor):
    app_config = apps.get_app_config("wallet")
    app_config.models_module = True
    create_permissions(app_config, apps=apps, verbosity=0)
    app_config.models_module = None

    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    group = Group.objects.get(name="Comptabilité")
    group.permissions.add(
        Permission.objects.get(content_type__app_label="wallet", codename="view_commission")
    )


class Migration(migrations.Migration):
    dependencies = [("wallet", "0006_commission")]

    operations = [
        migrations.RunSQL(FORWARD, BACKWARD),
        migrations.RunPython(grant_view, migrations.RunPython.noop),
    ]
