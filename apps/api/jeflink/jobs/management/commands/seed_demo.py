"""Données de démo locale : métiers, quartiers, comptes et demandes à chaque étape.

Idempotent : relançable. ``--reset`` vide d'abord les demandes, devis et avis.
Les comptes de démo partagent le mot de passe DEMO_PASSWORD (valeur de test, locale uniquement).
"""

from datetime import date, timedelta

from django.core.management.base import BaseCommand
from django.db import transaction

from jeflink.accounts.models import ProProfile, User
from jeflink.catalog.models import Trade, Zone
from jeflink.jobs import services
from jeflink.jobs.models import ServiceRequest

DEMO_PASSWORD = "jeflink-demo"
IMG = "/images/{}.webp"

TRADES = [
    {
        "slug": "plomberie",
        "name": "Plomberie",
        "tagline": "Fuites, débouchage, chasse d'eau, chauffe-eau, pompes et sanitaires.",
        "description": (
            "Une fuite sous l'évier, un WC qui coule, une pompe qui ne démarre plus : "
            "un plombier vérifié se déplace dans votre quartier, avec un devis clair avant "
            "d'intervenir."
        ),
        "services": [
            "Fuite et robinetterie",
            "Débouchage (évier, WC, douche)",
            "Chasse d'eau",
            "Chauffe-eau",
            "Pompe et surpresseur",
            "Pose de sanitaires",
        ],
        "starting_price": 5000,
        "icon": "bi-droplet",
        "image": IMG.format("metiers/plomberie"),
    },
    {
        "slug": "electricite",
        "name": "Électricité",
        "tagline": "Pannes, prises, éclairage, tableau électrique et raccordements.",
        "description": (
            "Coupure, disjoncteur qui saute, prise qui grésille ou nouveaux spots à poser : "
            "un électricien vérifié diagnostique, chiffre et répare en sécurité."
        ),
        "services": [
            "Panne et coupure de courant",
            "Prises et interrupteurs",
            "Éclairage",
            "Tableau électrique et disjoncteur",
            "Ventilateur de plafond",
            "Raccordement",
        ],
        "starting_price": 5000,
        "icon": "bi-lightning-charge",
        "image": IMG.format("metiers/electricite"),
    },
    {
        "slug": "climatisation",
        "name": "Froid et climatisation",
        "tagline": "Entretien et panne de clim, recharge de gaz, frigos et congélateurs.",
        "description": (
            "Avant les fortes chaleurs ou quand la clim ne refroidit plus : entretien, recharge "
            "de gaz, pose de split et dépannage de frigos et congélateurs."
        ),
        "services": [
            "Entretien de clim",
            "Panne de clim",
            "Recharge de gaz",
            "Pose de split",
            "Frigo ou congélateur en panne",
        ],
        "starting_price": 10000,
        "icon": "bi-snow",
        "image": IMG.format("metiers/climatisation"),
    },
    {
        "slug": "electromenager",
        "name": "Électroménager",
        "tagline": "Machine à laver, cuisinière, four, micro-ondes et petits appareils.",
        "description": (
            "Plutôt que de racheter, faites réparer : machine à laver, cuisinière, four, "
            "micro-ondes et petit électroménager, avec pièces annoncées dans le devis."
        ),
        "services": [
            "Machine à laver",
            "Cuisinière et four",
            "Micro-ondes",
            "Petit électroménager",
        ],
        "starting_price": 7500,
        "icon": "bi-plug",
        "image": IMG.format("metiers/electromenager"),
    },
    {
        "slug": "menage",
        "name": "Ménage",
        "tagline": "Ménage ponctuel, grand nettoyage, canapés et matelas.",
        "description": (
            "Un ménage ponctuel, un grand nettoyage avant d'emménager ou après des travaux, "
            "le shampoing des canapés et matelas : des équipes sérieuses et notées."
        ),
        "services": [
            "Ménage ponctuel",
            "Grand nettoyage (fin de travaux, déménagement)",
            "Canapés et matelas",
        ],
        "starting_price": 8000,
        "icon": "bi-stars",
        "image": IMG.format("metiers/menage"),
    },
    {
        "slug": "petits-travaux",
        "name": "Petits travaux",
        "tagline": "Peinture, menuiserie, maçonnerie légère, montage et fixations.",
        "description": (
            "Repeindre une chambre, réparer une porte, monter un meuble, fixer une étagère : "
            "les petits travaux qu'on repousse, faits proprement et au prix convenu."
        ),
        "services": [
            "Peinture",
            "Menuiserie",
            "Maçonnerie légère",
            "Montage de meubles",
            "Fixations",
        ],
        "starting_price": 10000,
        "icon": "bi-hammer",
        "image": IMG.format("metiers/petits-travaux"),
    },
]

ZONES = [
    "Almadies",
    "Cambérène",
    "Dieuppeul – Derklé",
    "Fann",
    "Fass – Colobane",
    "Grand Dakar",
    "Grand Yoff",
    "Guédiawaye",
    "Hann Bel-Air",
    "HLM",
    "Keur Massar",
    "Liberté",
    "Médina",
    "Mermoz",
    "Ngor",
    "Ouakam",
    "Parcelles Assainies",
    "Pikine",
    "Plateau",
    "Point E",
    "Sacré-Cœur",
    "Yoff",
]

CLIENTS = [
    {
        "email": "awa@demo.jeflink.sn",
        "first_name": "Awa",
        "last_name": "Ndiaye",
        "phone": "+221771234501",
    },
    {
        "email": "moussa@demo.jeflink.sn",
        "first_name": "Moussa",
        "last_name": "Diop",
        "phone": "+221781234502",
    },
    {
        "email": "aminata@demo.jeflink.sn",
        "first_name": "Aminata",
        "last_name": "Sy",
        "phone": "+221771234503",
    },
    {
        "email": "mariama@demo.jeflink.sn",
        "first_name": "Mariama",
        "last_name": "Faye",
        "phone": "+221771234504",
    },
    {
        "email": "babacar@demo.jeflink.sn",
        "first_name": "Babacar",
        "last_name": "Gueye",
        "phone": "+221771234505",
    },
    {
        "email": "pape@demo.jeflink.sn",
        "first_name": "Pape",
        "last_name": "Kane",
        "phone": "+221771234506",
    },
]

PROS = [
    {
        "email": "mamadou@demo.jeflink.sn",
        "first_name": "Mamadou",
        "last_name": "Fall",
        "phone": "+221771230011",
        "headline": "Plombier à Ouakam depuis 12 ans",
        "bio": "Fuites, chauffe-eau et pompes. Je viens avec les pièces courantes.",
        "trades": ["plomberie"],
        "zones": ["ouakam", "mermoz", "ngor", "almadies", "yoff"],
        "years": 12,
        "photo": IMG.format("pros/mamadou"),
    },
    {
        "email": "ousmane@demo.jeflink.sn",
        "first_name": "Ousmane",
        "last_name": "Sarr",
        "phone": "+221771230012",
        "headline": "Plomberie et sanitaires",
        "bio": "Pose de sanitaires et débouchage, devis gratuit.",
        "trades": ["plomberie"],
        "zones": [],
        "years": 6,
        "photo": IMG.format("pros/ousmane"),
    },
    {
        "email": "ibou@demo.jeflink.sn",
        "first_name": "Ibrahima",
        "last_name": "Ndiaye",
        "phone": "+221771230013",
        "headline": "Électricien bâtiment",
        "bio": "Tableaux, prises, éclairage. Travail propre et sécurisé.",
        "trades": ["electricite"],
        "zones": [],
        "years": 9,
        "photo": IMG.format("pros/ibrahima"),
    },
    {
        "email": "cheikh@demo.jeflink.sn",
        "first_name": "Cheikh",
        "last_name": "Mbaye",
        "phone": "+221771230014",
        "headline": "Frigoriste, clim et froid",
        "bio": "Entretien de clim avant l'été, recharge de gaz, pose de split.",
        "trades": ["climatisation", "electromenager"],
        "zones": [],
        "years": 8,
        "photo": IMG.format("pros/cheikh"),
    },
    {
        "email": "fatou@demo.jeflink.sn",
        "first_name": "Fatou",
        "last_name": "Diallo",
        "phone": "+221771230015",
        "headline": "Gérante, équipe de ménage (8 personnes)",
        "bio": "Ménage régulier ou grand nettoyage, canapés et matelas.",
        "trades": ["menage"],
        "zones": [],
        "years": 7,
        "photo": IMG.format("pros/fatou"),
    },
    {
        "email": "aliou@demo.jeflink.sn",
        "first_name": "Aliou",
        "last_name": "Ba",
        "phone": "+221771230016",
        "headline": "Peinture et petits travaux",
        "bio": "Peinture, menuiserie légère, montage de meubles.",
        "trades": ["petits-travaux"],
        "zones": [],
        "years": 5,
        "photo": IMG.format("pros/aliou"),
    },
]

ADMIN = {"email": "admin@jeflink.local", "first_name": "Équipe", "last_name": "Jeflink"}


def slugify_zone(name: str) -> str:
    from django.utils.text import slugify

    return slugify(name.replace("–", "-"))


class Command(BaseCommand):
    help = "Crée les données de démo (métiers, quartiers, comptes, demandes)."

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true", help="Supprime d'abord les demandes.")

    @transaction.atomic
    def handle(self, *args, reset=False, **options):
        if reset:
            ServiceRequest.objects.all().delete()

        for position, data in enumerate(TRADES):
            Trade.objects.update_or_create(
                slug=data["slug"], defaults={**data, "position": position}
            )
        for position, name in enumerate(ZONES):
            Zone.objects.update_or_create(
                slug=slugify_zone(name), defaults={"name": name, "position": position}
            )

        admin = self._user(ADMIN, is_staff=True, is_superuser=True)
        clients = {c["first_name"]: self._user(c) for c in CLIENTS}
        pros = {p["first_name"]: self._pro(p) for p in PROS}

        if not ServiceRequest.objects.exists():
            self._requests(clients, pros)

        self.stdout.write(
            self.style.SUCCESS(
                f"Démo prête : {Trade.objects.count()} métiers, {Zone.objects.count()} quartiers, "
                f"{len(clients)} clients, {len(pros)} pros, admin {admin.email}. "
                "Mot de passe commun : voir DEMO_PASSWORD dans seed_demo.py."
            )
        )

    def _user(self, data, **extra):
        fields = {k: v for k, v in data.items() if k in ("first_name", "last_name", "phone")}
        user, created = User.objects.get_or_create(
            email=data["email"], defaults={**fields, **extra}
        )
        # Photo de démo : celle du pro, sinon l'avatar client du même prénom.
        photo = data.get("photo") or IMG.format(f"clients/{data['first_name'].lower()}")
        if "@demo." in user.email and user.photo != photo:
            user.photo = photo
            user.save(update_fields=["photo"])
        if created:
            user.set_password(DEMO_PASSWORD)
            user.save()
        return user

    def _pro(self, data):
        user = self._user(data, role=User.Role.PRO)
        profile, _ = ProProfile.objects.update_or_create(
            user=user,
            defaults={
                "headline": data["headline"],
                "bio": data["bio"],
                "years_experience": data["years"],
                "photo": data["photo"],
                "is_verified": True,
            },
        )
        profile.trades.set(Trade.objects.filter(slug__in=data["trades"]))
        profile.zones.set(Zone.objects.filter(slug__in=data["zones"]))
        return user

    def _requests(self, clients, pros):
        awa, moussa = clients["Awa"], clients["Moussa"]
        trade = {t.slug: t for t in Trade.objects.all()}
        zone = {z.slug: z for z in Zone.objects.all()}
        soon = date.today() + timedelta(days=2)

        # Ouverte, deux devis reçus : Awa peut choisir.
        leak = services.create_request(
            awa,
            trade=trade["plomberie"],
            zone=zone["ouakam"],
            title="Fuite sous l'évier de la cuisine",
            description="L'eau coule sous l'évier dès qu'on ouvre le robinet.",
            landmark="Derrière la mosquée de la Divinité, portail vert",
            preferred_date=soon,
            is_urgent=True,
        )
        services.submit_quote(
            pros["Mamadou"], leak, 15000, "Changement du siphon et des joints, pièces comprises."
        )
        services.submit_quote(pros["Ousmane"], leak, 12500, "Diagnostic sur place, joints fournis.")

        # Réservée : Cheikh doit passer.
        clim = services.create_request(
            awa,
            trade=trade["climatisation"],
            zone=zone["ouakam"],
            title="La clim du salon ne refroidit plus",
            description="Split de 12 000 BTU, il souffle de l'air tiède depuis hier.",
            landmark="Même adresse : portail vert",
            preferred_date=soon,
        )
        quote = services.submit_quote(
            pros["Cheikh"], clim, 20000, "Contrôle, nettoyage et recharge de gaz si besoin."
        )
        services.accept_quote(awa, clim, quote.pk)

        # Terminée et notée.
        plug = services.create_request(
            awa,
            trade=trade["electricite"],
            zone=zone["ouakam"],
            title="Prise qui grésille dans la chambre",
            description="La prise chauffe et fait du bruit quand on branche le fer à repasser.",
        )
        quote = services.submit_quote(
            pros["Ibrahima"], plug, 7500, "Remplacement de la prise et contrôle du circuit."
        )
        services.accept_quote(awa, plug, quote.pk)
        services.complete(pros["Ibrahima"], plug)
        services.leave_review(awa, plug, 5, "Ponctuel, propre, et il a expliqué le problème.")

        # Ouverte sans devis : Ibrahima la voit dans « Demandes ouvertes ».
        services.create_request(
            moussa,
            trade=trade["electricite"],
            zone=zone["mermoz"],
            title="Poser 4 spots dans le salon",
            description="Les spots sont achetés, il faut les encastrer dans le faux plafond.",
            landmark="Villa à côté de la pharmacie Mermoz",
            preferred_date=date.today() + timedelta(days=5),
        )

        # Terminée et notée : ménage.
        clean = services.create_request(
            moussa,
            trade=trade["menage"],
            zone=zone["mermoz"],
            title="Grand nettoyage avant l'arrivée de la famille",
            description="Appartement F4, vitres comprises.",
        )
        quote = services.submit_quote(pros["Fatou"], clean, 35000, "Deux personnes, une journée.")
        services.accept_quote(moussa, clean, quote.pk)
        services.complete(moussa, clean)
        services.leave_review(moussa, clean, 4, "Très bon travail, un peu de retard le matin.")

        # Missions terminées et notées par d'autres clients (avis de la page Contact).
        past = [
            (
                "Aminata",
                "menage",
                "liberte",
                "Fatou",
                "Ménage complet d'un F3",
                30000,
                5,
                "Équipe à l'heure, appartement impeccable. Je les rappelle le mois prochain.",
            ),
            (
                "Mariama",
                "plomberie",
                "ouakam",
                "Mamadou",
                "Chauffe-eau qui ne chauffe plus",
                25000,
                5,
                "Le chauffe-eau remarche, et le prix est resté celui du devis.",
            ),
            (
                "Babacar",
                "climatisation",
                "mermoz",
                "Cheikh",
                "Entretien de deux clims",
                20000,
                4,
                "Bon entretien des deux clims, il a pris le temps de tout expliquer.",
            ),
            (
                "Pape",
                "petits-travaux",
                "grand-yoff",
                "Aliou",
                "Repeindre une chambre",
                45000,
                5,
                "Chambre repeinte en une journée, propre et sans traces.",
            ),
        ]
        for client, t, z, pro, title, amount, rating, comment in past:
            req = services.create_request(
                clients[client], trade=trade[t], zone=zone[z], title=title, description=title + "."
            )
            quote = services.submit_quote(pros[pro], req, amount, "Devis tout compris.")
            services.accept_quote(clients[client], req, quote.pk)
            services.complete(pros[pro], req)
            services.leave_review(clients[client], req, rating, comment)
