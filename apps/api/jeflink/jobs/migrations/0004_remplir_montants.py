"""Remplit les montants des missions réservées avant le lot 3 : prix du devis accepté, commission
au taux par défaut (10 %), sans remise."""

from django.db import migrations

DEFAULT_RATE = 10


def remplir(apps, schema_editor):
    ServiceRequest = apps.get_model("jobs", "ServiceRequest")
    Quote = apps.get_model("jobs", "Quote")
    accepted = dict(Quote.objects.filter(status="accepted").values_list("request_id", "amount"))
    for req in ServiceRequest.objects.filter(pk__in=accepted, price=None):
        req.price = accepted[req.pk]
        req.commission_rate = DEFAULT_RATE
        req.commission = (req.price * DEFAULT_RATE + 50) // 100
        req.save(update_fields=["price", "commission_rate", "commission"])


class Migration(migrations.Migration):
    dependencies = [("jobs", "0003_servicerequest_commission_and_more")]

    operations = [migrations.RunPython(remplir, migrations.RunPython.noop)]
