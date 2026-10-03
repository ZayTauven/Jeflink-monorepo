from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("accounts", "0005_devicesession_retiredrefreshtoken_and_more")]

    operations = [
        migrations.AddField(
            model_name="user",
            name="dormant_restricted_since",
            field=models.DateTimeField(blank=True, null=True),
        ),
        # Les sessions existantes gardent la politique de leur app (aucune session Ops n'existe).
        migrations.AddField(
            model_name="devicesession",
            name="policy",
            field=models.CharField(default="client", max_length=12),
            preserve_default=False,
        ),
        migrations.RunSQL(
            "UPDATE accounts_devicesession SET policy = app",
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
