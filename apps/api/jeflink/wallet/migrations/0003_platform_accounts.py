"""Comptes de la plateforme (spec 005). Les comptes ``platform_collections`` naissent avec les
canaux de règlement (tâche 4) ; ceux d'un pro, à son premier mouvement."""

from django.db import migrations

PLATFORM_KINDS = ("platform_revenue", "platform_goodwill")


def create_accounts(apps, schema_editor):
    LedgerAccount = apps.get_model("wallet", "LedgerAccount")
    for kind in PLATFORM_KINDS:
        LedgerAccount.objects.get_or_create(kind=kind, provider=None)


class Migration(migrations.Migration):
    dependencies = [("wallet", "0002_ledger_guarantees")]

    operations = [migrations.RunPython(create_accounts, migrations.RunPython.noop)]
