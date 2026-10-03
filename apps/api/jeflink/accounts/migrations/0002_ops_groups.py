"""Profils Ops (groupes) et leurs permissions accounts (spec 001, « Rôles et permissions »)."""

from django.contrib.auth.management import create_permissions
from django.db import migrations

GROUP_PERMISSIONS = {
    "Support": ["ops_accounts_view", "ops_accounts_manage"],
    "Validation KYC": ["ops_accounts_view"],
    "Finance": ["ops_accounts_view"],
    # Seul le groupe Admin peut changer un numéro (S2).
    "Admin": ["ops_accounts_view", "ops_accounts_manage", "ops_accounts_change_phone"],
}


def create_groups(apps, schema_editor):
    # Les permissions naissent au post_migrate : on les crée maintenant pour pouvoir les lier.
    app_config = apps.get_app_config("accounts")
    app_config.models_module = True
    create_permissions(app_config, apps=apps, verbosity=0)
    app_config.models_module = None

    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    for name, codenames in GROUP_PERMISSIONS.items():
        group, _ = Group.objects.get_or_create(name=name)
        group.permissions.add(
            *Permission.objects.filter(content_type__app_label="accounts", codename__in=codenames)
        )


def delete_groups(apps, schema_editor):
    apps.get_model("auth", "Group").objects.filter(name__in=GROUP_PERMISSIONS).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0001_initial"),
        ("auth", "0012_alter_user_first_name_max_length"),
        ("contenttypes", "0002_remove_content_type_name"),
    ]

    operations = [migrations.RunPython(create_groups, delete_groups)]
