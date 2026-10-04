# Horodatages du déroulé, fenêtre de contestation et montant d'origine (spec 004, tâche 2).

from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('bookings', '0002_bookingevent_immutable'),
        ('providers', '0002_validation_pros_group'),
        ('requests', '0003_quotes'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='booking',
            name='closed_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='booking',
            name='completed_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='booking',
            name='dispute_deadline',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='booking',
            name='dispute_reminder_sent_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='booking',
            name='en_route_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='booking',
            name='on_site_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='booking',
            name='original_amount_xof',
            field=models.PositiveBigIntegerField(default=0),
            preserve_default=False,
        ),
        # Les réservations existantes gardent leur montant comme montant d'origine.
        migrations.RunSQL(
            "UPDATE bookings_booking SET original_amount_xof = amount_xof",
            migrations.RunSQL.noop,
        ),
        migrations.AddField(
            model_name='booking',
            name='started_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddIndex(
            model_name='booking',
            index=models.Index(fields=['status', 'dispute_deadline'], name='bookings_bo_status_60918e_idx'),
        ),
        migrations.AddConstraint(
            model_name='booking',
            constraint=models.CheckConstraint(condition=models.Q(('original_amount_xof__gt', 0)), name='booking_original_amount_positive'),
        ),
    ]
