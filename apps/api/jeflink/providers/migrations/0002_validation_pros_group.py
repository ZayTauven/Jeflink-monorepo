"""Groupe « Validation pros » (spec 003) : voir les fiches, les vérifier et les suspendre.

Le compte qui valide est un compte technique de l'admin Django, comme « Saisie catalogue ».
"""

from django.contrib.auth.management import create_permissions
from django.db import migrations

GROUP_NAME = "Validation pros"
CODENAMES = ("view_provider", "verify_provider")


def create_group(apps, schema_editor):
    app_config = apps.get_app_config("providers")
    app_config.models_module = True
    create_permissions(app_config, apps=apps, verbosity=0)
    app_config.models_module = None

    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    group, _ = Group.objects.get_or_create(name=GROUP_NAME)
    group.permissions.add(
        *Permission.objects.filter(content_type__app_label="providers", codename__in=CODENAMES)
    )


def delete_group(apps, schema_editor):
    apps.get_model("auth", "Group").objects.filter(name=GROUP_NAME).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("providers", "0001_initial"),
        ("auth", "0012_alter_user_first_name_max_length"),
        ("contenttypes", "0002_remove_content_type_name"),
    ]

    operations = [migrations.RunPython(create_group, delete_group)]
