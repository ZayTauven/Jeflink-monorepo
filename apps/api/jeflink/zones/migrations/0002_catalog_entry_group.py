"""Groupe « Saisie catalogue » (spec 002) : ajouter et modifier métiers, services et zones dans l'admin.

Jamais de suppression (on désactive). Le compte qui saisit est un compte technique (Q6).
"""

from django.contrib.auth.management import create_permissions
from django.db import migrations

GROUP_NAME = "Saisie catalogue"
MODELS = {"catalog": ("trade", "service"), "zones": ("city", "zone")}


def create_group(apps, schema_editor):
    # Les permissions naissent au post_migrate : on les crée maintenant pour pouvoir les lier.
    for label in MODELS:
        app_config = apps.get_app_config(label)
        app_config.models_module = True
        create_permissions(app_config, apps=apps, verbosity=0)
        app_config.models_module = None

    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    group, _ = Group.objects.get_or_create(name=GROUP_NAME)
    for label, models in MODELS.items():
        codenames = [f"{action}_{model}" for model in models for action in ("add", "change")]
        group.permissions.add(
            *Permission.objects.filter(content_type__app_label=label, codename__in=codenames)
        )


def delete_group(apps, schema_editor):
    apps.get_model("auth", "Group").objects.filter(name=GROUP_NAME).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("zones", "0001_initial"),
        ("catalog", "0001_initial"),
        ("auth", "0012_alter_user_first_name_max_length"),
        ("contenttypes", "0002_remove_content_type_name"),
    ]

    operations = [migrations.RunPython(create_group, delete_group)]
