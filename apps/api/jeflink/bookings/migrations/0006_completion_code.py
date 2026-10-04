# Code de fin de mission (spec 004, tâche 4). Généré par Django le 2026-10-03 21:07

from django.db import migrations, models


def backfill_codes(apps, schema_editor):
    """Un code pour les missions déjà planifiées ou en cours avant cette fonctionnalité."""
    import secrets

    from django.conf import settings

    from jeflink.common import crypto

    Booking = apps.get_model("bookings", "Booking")
    digits = settings.COMPLETION_CODE_DIGITS
    live = Booking.objects.filter(
        status__in=["scheduled", "en_route", "on_site", "in_progress"], completion_code_enc=""
    )
    for booking in live:
        booking.completion_code_enc = crypto.encrypt(str(secrets.randbelow(10**digits)).zfill(digits))
        booking.save(update_fields=["completion_code_enc"])


class Migration(migrations.Migration):

    dependencies = [
        ('bookings', '0005_mediation_group'),
    ]

    operations = [
        migrations.AddField(
            model_name='booking',
            name='completion_code_attempts',
            field=models.PositiveSmallIntegerField(default=0),
        ),
        migrations.AddField(
            model_name='booking',
            name='completion_code_enc',
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name='booking',
            name='completion_code_locked',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='booking',
            name='completion_code_regenerations',
            field=models.PositiveSmallIntegerField(default=0),
        ),
        migrations.AddField(
            model_name='booking',
            name='completion_code_sms_sent',
            field=models.PositiveSmallIntegerField(default=0),
        ),
        migrations.AddField(
            model_name='booking',
            name='completion_method',
            field=models.CharField(blank=True, choices=[('code', 'Code de fin'), ('no_code', 'Sans code')], max_length=7),
        ),
        migrations.AddField(
            model_name='booking',
            name='no_code_reason',
            field=models.CharField(blank=True, max_length=16),
        ),
        migrations.RunPython(backfill_codes, migrations.RunPython.noop),
    ]
