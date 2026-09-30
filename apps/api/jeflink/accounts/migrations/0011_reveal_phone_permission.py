"""Permission dédiée à l'affichage du numéro complet, réservée à Support et Admin.

Décision de Zay (revue sécurité de la tâche 15, I1) : Finance et Validation KYC ne voient plus
que le numéro masqué ; la révélation exige en plus un TOTP de moins de 5 min.
"""

from django.contrib.auth.management import create_permissions
from django.db import migrations

GROUPS = ("Support", "Admin")
CODENAME = "ops_accounts_reveal_phone"


def grant(apps, schema_editor):
    app_config = apps.get_app_config("accounts")
    app_config.models_module = True
    create_permissions(app_config, apps=apps, verbosity=0)
    app_config.models_module = None

    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    permission = Permission.objects.get(content_type__app_label="accounts", codename=CODENAME)
    for group in Group.objects.filter(name__in=GROUPS):
        group.permissions.add(permission)


def revoke(apps, schema_editor):
    Permission = apps.get_model("auth", "Permission")
    Permission.objects.filter(content_type__app_label="accounts", codename=CODENAME).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0010_ops_totp"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="user",
            options={
                "permissions": [
                    ("ops_accounts_view", "Ops : consulter les comptes"),
                    ("ops_accounts_manage", "Ops : gérer les comptes (sessions, blocages, état)"),
                    ("ops_accounts_change_phone", "Ops : changer le numéro d'un compte"),
                    ("ops_accounts_reveal_phone", "Ops : afficher le numéro complet d'un compte"),
                ]
            },
        ),
        migrations.RunPython(grant, revoke),
    ]
