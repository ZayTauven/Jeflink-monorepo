"""« Saisie catalogue » lit les demandes non servies : elles disent quel métier ouvrir où."""

from django.contrib.auth.management import create_permissions
from django.db import migrations

GROUP_NAME = "Saisie catalogue"
CODENAME = "view_unserveddemand"


def grant(apps, schema_editor):
    app_config = apps.get_app_config("analytics")
    app_config.models_module = True
    create_permissions(app_config, apps=apps, verbosity=0)
    app_config.models_module = None

    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    group = Group.objects.get(name=GROUP_NAME)
    group.permissions.add(
        Permission.objects.get(content_type__app_label="analytics", codename=CODENAME)
    )


def revoke(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    group = Group.objects.filter(name=GROUP_NAME).first()
    if group:
        group.permissions.remove(
            *Permission.objects.filter(content_type__app_label="analytics", codename=CODENAME)
        )


class Migration(migrations.Migration):
    dependencies = [
        ("analytics", "0001_initial"),
        ("zones", "0002_catalog_entry_group"),
        ("auth", "0012_alter_user_first_name_max_length"),
        ("contenttypes", "0002_remove_content_type_name"),
    ]

    operations = [migrations.RunPython(grant, revoke)]
