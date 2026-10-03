"""Groupe « Médiation » (spec 004) : voir et trancher les no-shows contestés dans l'admin.

Compte technique de l'admin Django, comme « Validation pros ». Les litiges s'y ajoutent à la
tâche 7 (migration de ``trust``).
"""

from django.contrib.auth.management import create_permissions
from django.db import migrations

GROUP_NAME = "Médiation"
CODENAMES = ("view_noshowreport", "decide_noshowreport")


def create_group(apps, schema_editor):
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


def delete_group(apps, schema_editor):
    apps.get_model("auth", "Group").objects.filter(name=GROUP_NAME).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("bookings", "0004_no_show_report"),
        ("auth", "0012_alter_user_first_name_max_length"),
        ("contenttypes", "0002_remove_content_type_name"),
    ]

    operations = [migrations.RunPython(create_group, delete_group)]
