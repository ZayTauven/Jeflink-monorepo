"""Groupe « Rapprochement » (spec 005, tâche 5) : voir les portefeuilles, le grand livre et les
déclarations ; confirmer, renvoyer à corriger ou rejeter une déclaration ; saisir un versement vu
dans le relevé ou des espèces remises au bureau. Comptes techniques nommés, second facteur, et un
code TOTP frais pour chaque écriture."""

from django.contrib.auth.management import create_permissions
from django.db import migrations

GROUP_NAME = "Rapprochement"
PERMISSIONS = {
    "payments": ("view_paymentintent", "view_settlementchannel", "decide_paymentintent"),
    "wallet": (
        "view_ledgeraccount",
        "view_ledgertransaction",
        "view_ledgerentry",
        "view_commission",
    ),
}


def create_group(apps, schema_editor):
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


def delete_group(apps, schema_editor):
    apps.get_model("auth", "Group").objects.filter(name=GROUP_NAME).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("payments", "0003_decide_permission"),
        ("wallet", "0007_commission_immutable"),
        ("auth", "0012_alter_user_first_name_max_length"),
        ("contenttypes", "0002_remove_content_type_name"),
    ]

    operations = [migrations.RunPython(create_group, delete_group)]
