from django.core.validators import MaxValueValidator
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
    commission_percent = models.PositiveSmallIntegerField(
        "commission (%)",
        null=True,
        blank=True,
        validators=[MaxValueValidator(50)],
        help_text="Vide : taux par défaut de la plateforme.",
    )

    class Meta:
        ordering = ["position", "name"]
        verbose_name = "métier"

    def __str__(self):
        return self.name


class City(models.Model):
    """Ville desservie, rattachée à une des 14 régions du Sénégal. Une ville fermée retire ses
    quartiers du site (la démo n'ouvre que Dakar)."""

    class Region(models.TextChoices):
        DAKAR = "dakar", "Dakar"
        THIES = "thies", "Thiès"
        SAINT_LOUIS = "saint-louis", "Saint-Louis"
        DIOURBEL = "diourbel", "Diourbel"
        LOUGA = "louga", "Louga"
        FATICK = "fatick", "Fatick"
        KAOLACK = "kaolack", "Kaolack"
        KAFFRINE = "kaffrine", "Kaffrine"
        MATAM = "matam", "Matam"
        TAMBACOUNDA = "tambacounda", "Tambacounda"
        KEDOUGOU = "kedougou", "Kédougou"
        KOLDA = "kolda", "Kolda"
        SEDHIOU = "sedhiou", "Sédhiou"
        ZIGUINCHOR = "ziguinchor", "Ziguinchor"

    slug = models.SlugField(unique=True)
    name = models.CharField("nom", max_length=80)
    region = models.CharField("région", max_length=12, choices=Region.choices)
    position = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField("ouverte", default=True)

    class Meta:
        ordering = ["position", "name"]
        verbose_name = "ville"

    def __str__(self):
        return self.name


def default_city() -> int:
    """Dakar par défaut : la démo ne couvre que Dakar (créée au besoin)."""
    city, _ = City.objects.get_or_create(
        slug="dakar", defaults={"name": "Dakar", "region": City.Region.DAKAR}
    )
    return city.pk


class Zone(models.Model):
    """Un quartier ou une commune desservie, dans une ville."""

    slug = models.SlugField(unique=True)
    name = models.CharField("nom", max_length=80)
    city = models.ForeignKey(
        City,
        on_delete=models.PROTECT,
        related_name="zones",
        verbose_name="ville",
        default=default_city,
    )
    position = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField("actif", default=True)

    class Meta:
        ordering = ["position", "name"]
        verbose_name = "quartier"

    def __str__(self):
        return self.name

    @property
    def is_served(self) -> bool:
        return self.is_active and self.city.is_active


def served_zones():
    """Quartiers ouverts dans une ville ouverte : ceux du site, des demandes et des pros."""
    return Zone.objects.filter(is_active=True, city__is_active=True).select_related("city")


class Campaign(models.Model):
    """Bandeau d'annonce sur le site (accueil, formulaire de demande), sur une période."""

    class Placement(models.TextChoices):
        HOME = "home", "Accueil"
        REQUEST = "request", "Formulaire de demande"
        BOTH = "both", "Accueil et formulaire"

    title = models.CharField("titre", max_length=80)
    message = models.CharField("message", max_length=200)
    cta_label = models.CharField("texte du bouton", max_length=40, blank=True)
    cta_url = models.CharField(
        "lien du bouton", max_length=200, blank=True, help_text="Page du site, ex. /metiers/menage"
    )
    coupon = models.ForeignKey(
        "jobs.Coupon",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="campaigns",
        verbose_name="code promo affiché",
    )
    placement = models.CharField(
        "emplacement", max_length=10, choices=Placement.choices, default=Placement.HOME
    )
    starts_at = models.DateTimeField("début", null=True, blank=True)
    ends_at = models.DateTimeField("fin", null=True, blank=True)
    is_active = models.BooleanField("active", default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "campagne"

    def __str__(self):
        return self.title
