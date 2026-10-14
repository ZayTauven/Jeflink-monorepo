"""Villes : le texte « ville » des quartiers devient une vraie ville, rattachée à sa région."""

import django.db.models.deletion
from django.db import migrations, models
from django.utils.text import slugify

import jeflink.catalog.models

# Région devinée d'après le nom (les villes existantes ; Dakar sinon).
REGIONS = {
    "dakar": "dakar",
    "pikine": "dakar",
    "guediawaye": "dakar",
    "rufisque": "dakar",
    "thies": "thies",
    "mbour": "thies",
    "saint-louis": "saint-louis",
    "touba": "diourbel",
    "diourbel": "diourbel",
    "kaolack": "kaolack",
    "ziguinchor": "ziguinchor",
}


def create_cities(apps, schema_editor):
    City = apps.get_model("catalog", "City")
    Zone = apps.get_model("catalog", "Zone")
    for zone in Zone.objects.all():
        name = (zone.city_name or "Dakar").strip() or "Dakar"
        slug = slugify(name) or "dakar"
        city, _ = City.objects.get_or_create(
            slug=slug, defaults={"name": name, "region": REGIONS.get(slug, "dakar")}
        )
        zone.city_ref = city
        zone.save(update_fields=["city_ref"])


def back_to_text(apps, schema_editor):
    Zone = apps.get_model("catalog", "Zone")
    for zone in Zone.objects.select_related("city_ref"):
        zone.city_name = zone.city_ref.name if zone.city_ref else "Dakar"
        zone.save(update_fields=["city_name"])


class Migration(migrations.Migration):
    dependencies = [("catalog", "0003_campaign_coupon")]

    operations = [
        migrations.CreateModel(
            name="City",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("slug", models.SlugField(unique=True)),
                ("name", models.CharField(max_length=80, verbose_name="nom")),
                (
                    "region",
                    models.CharField(
                        choices=jeflink.catalog.models.City.Region.choices,
                        max_length=12,
                        verbose_name="région",
                    ),
                ),
                ("position", models.PositiveSmallIntegerField(default=0)),
                ("is_active", models.BooleanField(default=True, verbose_name="ouverte")),
            ],
            options={"verbose_name": "ville", "ordering": ["position", "name"]},
        ),
        migrations.RenameField("zone", "city", "city_name"),
        migrations.AddField(
            "zone",
            "city_ref",
            models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="+",
                to="catalog.city",
            ),
        ),
        migrations.RunPython(create_cities, back_to_text),
        migrations.RemoveField("zone", "city_name"),
        migrations.RenameField("zone", "city_ref", "city"),
        migrations.AlterField(
            "zone",
            "city",
            models.ForeignKey(
                default=jeflink.catalog.models.default_city,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="zones",
                to="catalog.city",
                verbose_name="ville",
            ),
        ),
    ]
