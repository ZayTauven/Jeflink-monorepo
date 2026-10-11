from django.db import models


class Trade(models.Model):
    """Un métier (plomberie, électricité…). Donnée administrée, jamais une liste en dur."""

    slug = models.SlugField(unique=True)
    name = models.CharField("nom", max_length=80)
    tagline = models.CharField("résumé", max_length=180, blank=True)
    description = models.TextField(blank=True)
    services = models.JSONField(
        "prestations courantes", default=list, blank=True, help_text='Liste JSON : ["Fuite", …]'
    )
    starting_price = models.PositiveIntegerField(
        "à partir de (F CFA)", null=True, blank=True, help_text="Entier en F CFA, sans décimales."
    )
    icon = models.CharField(
        "icône", max_length=40, blank=True, help_text="Classe Bootstrap Icons, ex. bi-droplet"
    )
    image = models.CharField(
        "image", max_length=200, blank=True, help_text="Chemin d'image servi par le site web."
    )
    position = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField("actif", default=True)

    class Meta:
        ordering = ["position", "name"]
        verbose_name = "métier"

    def __str__(self):
        return self.name


class Zone(models.Model):
    """Un quartier ou une commune desservie."""

    slug = models.SlugField(unique=True)
    name = models.CharField("nom", max_length=80)
    city = models.CharField("ville", max_length=80, default="Dakar")
    position = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField("actif", default=True)

    class Meta:
        ordering = ["position", "name"]
        verbose_name = "quartier"

    def __str__(self):
        return self.name
