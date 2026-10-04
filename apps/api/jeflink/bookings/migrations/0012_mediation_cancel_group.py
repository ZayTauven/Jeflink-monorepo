"""Groupe « Médiation » : voir les réservations et annuler une mission bloquée (revue sécurité)."""

from django.contrib.auth.management import create_permissions
from django.db import migrations

GROUP_NAME = "Médiation"
CODENAMES = ("view_booking", "cancel_booking_ops")


def add_permissions(apps, schema_editor):
    app_config = apps.get_app_config("bookings")
    app_config.models_module = True
    create_permissions(app_config, apps=apps, verbosity=0)
    app_config.models_module = None
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    group, _ = Group.objects.get_or_create(name=GROUP_NAME)
    group.permissions.add(
        *Permission.objects.filter(content_type__app_label="bookings", codename__in=CODENAMES)
    )


def remove_permissions(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    group = Group.objects.filter(name=GROUP_NAME).first()
    if group is not None:
        group.permissions.remove(
            *Permission.objects.filter(content_type__app_label="bookings", codename__in=CODENAMES)
        )


class Migration(migrations.Migration):
    dependencies = [
        ("bookings", "0011_booking_stuck_and_permission"),
        ("auth", "0012_alter_user_first_name_max_length"),
        ("contenttypes", "0002_remove_content_type_name"),
    ]

    operations = [migrations.RunPython(add_permissions, remove_permissions)]
