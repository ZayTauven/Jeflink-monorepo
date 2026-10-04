"""« Saisie catalogue » rattache à une zone les demandes au quartier inconnu (spec 003).

Il ne voit ni repère, ni position, ni description : l'admin les masque.
"""

from django.contrib.auth.management import create_permissions
from django.db import migrations

GROUP_NAME = "Saisie catalogue"
CODENAMES = ("view_servicerequest", "attach_servicerequest")


def grant(apps, schema_editor):
    app_config = apps.get_app_config("requests")
    app_config.models_module = True
    create_permissions(app_config, apps=apps, verbosity=0)
    app_config.models_module = None

    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    group = Group.objects.get(name=GROUP_NAME)
    group.permissions.add(
        *Permission.objects.filter(content_type__app_label="requests", codename__in=CODENAMES)
    )


def revoke(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    group = Group.objects.filter(name=GROUP_NAME).first()
    if group:
        group.permissions.remove(
            *Permission.objects.filter(content_type__app_label="requests", codename__in=CODENAMES)
        )


class Migration(migrations.Migration):
    dependencies = [
        ("requests", "0001_initial"),
        ("zones", "0002_catalog_entry_group"),
        ("auth", "0012_alter_user_first_name_max_length"),
        ("contenttypes", "0002_remove_content_type_name"),
    ]

    operations = [migrations.RunPython(grant, revoke)]
