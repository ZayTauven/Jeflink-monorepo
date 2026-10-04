"""Groupe « Médiation » (spec 004, tâche 7) : trancher les litiges, voir les photos d'un litige et
réafficher une photo signalée. S'ajoute aux droits sur les no-shows (migration 0005)."""

from django.contrib.auth.management import create_permissions
from django.db import migrations

GROUP_NAME = "Médiation"
PERMISSIONS = {
    "trust": ("view_dispute", "decide_dispute"),
    "bookings": ("view_bookingphoto", "restore_bookingphoto"),
}


def add_permissions(apps, schema_editor):
    for label in PERMISSIONS:
        app_config = apps.get_app_config(label)
        app_config.models_module = True
        create_permissions(app_config, apps=apps, verbosity=0)
        app_config.models_module = None

    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    group, _ = Group.objects.get_or_create(name=GROUP_NAME)
    for label, codenames in PERMISSIONS.items():
        group.permissions.add(
            *Permission.objects.filter(content_type__app_label=label, codename__in=codenames)
        )


def remove_permissions(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    group = Group.objects.filter(name=GROUP_NAME).first()
    if group is not None:
        for label, codenames in PERMISSIONS.items():
            group.permissions.remove(
                *Permission.objects.filter(content_type__app_label=label, codename__in=codenames)
            )


class Migration(migrations.Migration):
    dependencies = [
        ("bookings", "0009_alter_bookingphoto_options"),
        ("trust", "0005_dispute"),
        ("auth", "0012_alter_user_first_name_max_length"),
        ("contenttypes", "0002_remove_content_type_name"),
    ]

    operations = [migrations.RunPython(add_permissions, remove_permissions)]
