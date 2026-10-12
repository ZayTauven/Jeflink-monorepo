"""Données de démo locale : métiers, quartiers, comptes et demandes à chaque étape.

Idempotent : relançable. ``--reset`` vide d'abord les demandes, devis et avis.
Les comptes de démo partagent le mot de passe DEMO_PASSWORD (valeur de test, locale uniquement).
"""

import random
from datetime import date, timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from jeflink.accounts.models import ContactMessage, ProProfile, User
from jeflink.catalog.models import Trade, Zone
from jeflink.console.models import AuditLog
from jeflink.jobs import services
from jeflink.jobs.models import Dispute, Quote, RequestEvent, Review, ServiceRequest

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

# --- Historique de la console : 90 jours d'activité inventée, reproductible (graine fixe) -------

HISTORY_DAYS = 90
HISTORY_SIZE = 70
HISTORY_CLIENTS = [
    ("Khady", "Sow"),
    ("Mame", "Diop"),
    ("Serigne", "Mbacké"),
    ("Coumba", "Ndour"),
    ("Abdou", "Thiam"),
    ("Ndèye", "Seck"),
    ("Modou", "Cissé"),
    ("Astou", "Diagne"),
    ("Lamine", "Camara"),
    ("Binta", "Sy"),
    ("Ousseynou", "Lo"),
    ("Rokhaya", "Niang"),
]
# Inscriptions de pros que l'équipe n'a pas encore vérifiées (file « À vérifier »).
PENDING_PROS = [
    ("Saliou", "Diouf", "plomberie", "Plombier, 4 ans d'expérience à Pikine"),
    ("Adama", "Touré", "electricite", "Électricien, installations neuves et dépannage"),
    ("Yacine", "Kébé", "menage", "Équipe de ménage (3 personnes), Parcelles Assainies"),
]
CONTACT_MESSAGES = [
    (
        "Société Teranga Bureaux",
        "contact@teranga-bureaux.example",
        "Bonjour, nous cherchons un contrat d'entretien des clims pour 12 bureaux au Plateau.",
    ),
    (
        "Mbaye Diagne",
        "mbaye.diagne@example.com",
        "Je suis plombier à Rufisque, comment rejoindre Jeflink ?",
    ),
]
# (titre, description, prix de base en F CFA) par métier ; poids = part des demandes.
HISTORY_JOBS = {
    "plomberie": (
        30,
        [
            ("Fuite au robinet de la cuisine", "Le robinet goutte en continu.", 7500),
            ("WC bouché", "La chasse d'eau ne descend plus.", 10000),
            ("Chauffe-eau en panne", "Plus d'eau chaude depuis deux jours.", 25000),
            ("Pompe qui ne démarre plus", "Le surpresseur fait du bruit sans pomper.", 20000),
            ("Pose d'un lavabo", "Lavabo et mitigeur achetés.", 15000),
        ],
    ),
    "electricite": (
        22,
        [
            ("Disjoncteur qui saute", "Le courant coupe quand on allume la clim.", 10000),
            ("Ajouter des prises", "Trois prises dans le salon.", 12000),
            ("Lustre à installer", "Plafond à 3 m, le lustre est acheté.", 8000),
            ("Tableau électrique à refaire", "Vieux tableau, fusibles à remplacer.", 45000),
        ],
    ),
    "climatisation": (
        18,
        [
            ("Entretien de clim", "Deux splits à nettoyer avant l'été.", 15000),
            ("Clim qui coule", "De l'eau coule du split de la chambre.", 12000),
            ("Pose d'un split", "Split 12 000 BTU neuf à installer.", 35000),
        ],
    ),
    "menage": (
        15,
        [
            ("Ménage complet d'un F3", "Appartement au 2e étage.", 25000),
            ("Nettoyage de canapé", "Canapé d'angle en tissu.", 15000),
            ("Grand nettoyage après travaux", "Poussière de peinture partout.", 40000),
        ],
    ),
    "electromenager": (
        8,
        [
            ("Frigo qui ne refroidit plus", "Le congélateur marche, pas le frigo.", 15000),
            ("Machine à laver en panne", "Elle ne vidange plus.", 12000),
        ],
    ),
    "petits-travaux": (
        7,
        [
            ("Monter une armoire", "Armoire 3 portes en kit.", 10000),
            ("Repeindre un salon", "Murs et plafond, peinture fournie.", 50000),
        ],
    ),
}
COMMENTS = {
    5: ["Travail propre et rapide.", "Très professionnel, je recommande.", ""],
    4: ["Bon travail, un peu de retard.", "Satisfait, prix respecté.", ""],
    3: ["Correct, mais il a fallu rappeler deux fois.", ""],
    2: ["Le problème est revenu au bout de trois jours."],
    1: ["Pas venu au premier rendez-vous, travail bâclé."],
}


def slugify_zone(name: str) -> str:
    from django.utils.text import slugify

    return slugify(name.replace("–", "-"))


class Command(BaseCommand):
    help = "Crée les données de démo (métiers, quartiers, comptes, demandes)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Supprime d'abord les demandes et le journal de la console.",
        )

    @transaction.atomic
    def handle(self, *args, reset=False, **options):
        if reset:
            ServiceRequest.objects.all().delete()
            AuditLog.objects.all().delete()  # il pointerait vers des demandes disparues

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
            self._spread_showcase()
            self._history(pros)
            self._disputes()
        self._pending_pros()
        if not ContactMessage.objects.exists():
            for name, email, message in CONTACT_MESSAGES:
                ContactMessage.objects.create(name=name, email=email, message=message)

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

    def _disputes(self):
        """Deux litiges sur les missions notées 2/5 ou moins : un ouvert, un en cours."""
        low = Review.objects.filter(rating__lte=2).select_related("request__client")[:2]
        details = [
            ("quality", "Le problème est revenu trois jours après l'intervention."),
            ("price", "Le pro a demandé 5 000 F CFA de plus que le devis sur place."),
        ]
        for review, (reason, text) in zip(low, details, strict=False):
            req = review.request
            dispute = services.open_dispute(req.client, req, reason, text)
            Dispute.objects.filter(pk=dispute.pk).update(created_at=review.created_at)
        first = Dispute.objects.order_by("pk").first()
        if first:
            Dispute.objects.filter(pk=first.pk).update(status=Dispute.Status.INVESTIGATING)

    def _spread_showcase(self):
        """Étale les missions terminées de la vitrine sur les trois dernières semaines.

        Leurs avis gardent la date du jour : ce sont eux que le site montre en premier.
        """
        now = timezone.now()
        done = ServiceRequest.objects.filter(status=ServiceRequest.Status.DONE).order_by("pk")
        for i, req in enumerate(done):
            t0 = now - timedelta(days=4 + 3 * i, hours=5)
            ServiceRequest.objects.filter(pk=req.pk).update(
                created_at=t0, updated_at=t0 + timedelta(hours=30)
            )
            for status, hours in (("open", 0), ("booked", 6), ("done", 30)):
                RequestEvent.objects.filter(request=req, status=status).update(
                    created_at=t0 + timedelta(hours=hours)
                )
            req.quotes.update(created_at=t0 + timedelta(hours=2))

    def _pending_pros(self):
        joined = timezone.now() - timedelta(days=1)
        for i, (first, last, trade, headline) in enumerate(PENDING_PROS):
            user, created = User.objects.get_or_create(
                email=f"{first.lower()}.{slugify_zone(last)}@pros.jeflink.local",
                defaults={"first_name": first, "last_name": last, "role": User.Role.PRO},
            )
            if created:
                user.set_password(DEMO_PASSWORD)
                user.date_joined = joined - timedelta(days=i * 2, hours=i * 5)
                user.save()
            profile, _ = ProProfile.objects.get_or_create(
                user=user, defaults={"headline": headline, "years_experience": 2 + i}
            )
            profile.trades.set(Trade.objects.filter(slug=trade))

    def _history(self, pros):
        """~70 demandes sur 90 jours, à toutes les étapes, pour les graphiques de la console.

        Les règles passent par ``services`` ; seules les dates sont ensuite antidatées.
        """
        rng = random.Random(2026)
        now = timezone.now()
        clients = [
            self._user(
                {
                    "email": f"{first.lower()}.{slugify_zone(last)}@clients.jeflink.local",
                    "first_name": first,
                    "last_name": last,
                    "phone": f"+22177600{i:04d}",
                }
            )
            for i, (first, last) in enumerate(HISTORY_CLIENTS)
        ]
        for client in clients:
            if client.date_joined > now - timedelta(days=HISTORY_DAYS):
                User.objects.filter(pk=client.pk).update(
                    date_joined=now - timedelta(days=HISTORY_DAYS + rng.randint(1, 60))
                )
        trades = {t.slug: t for t in Trade.objects.all()}
        zones = list(Zone.objects.all())
        busy = [z for z in zones if z.slug in {"ouakam", "mermoz", "yoff", "liberte", "plateau"}]
        by_trade = {
            "plomberie": [pros["Mamadou"], pros["Ousmane"]],
            "electricite": [pros["Ibrahima"]],
            "climatisation": [pros["Cheikh"]],
            "electromenager": [pros["Cheikh"]],
            "menage": [pros["Fatou"]],
            "petits-travaux": [pros["Aliou"]],
        }
        slugs = list(HISTORY_JOBS)
        weights = [HISTORY_JOBS[s][0] for s in slugs]
        hour = timedelta(hours=1)

        for _ in range(HISTORY_SIZE):
            # Plus de demandes récentes que d'anciennes : la plateforme grandit.
            age = timedelta(days=HISTORY_DAYS * rng.random() ** 1.5, hours=rng.randint(0, 23))
            t0 = now - age - hour
            slug = rng.choices(slugs, weights)[0]
            title, description, base = rng.choice(HISTORY_JOBS[slug][1])
            client = rng.choice(clients)
            req = services.create_request(
                client,
                trade=trades[slug],
                zone=rng.choice(busy if rng.random() < 0.5 else zones),
                title=title,
                description=description,
                is_urgent=rng.random() < 0.15,
            )
            ServiceRequest.objects.filter(pk=req.pk).update(created_at=t0, updated_at=t0)
            RequestEvent.objects.filter(request=req).update(created_at=t0)

            roll = rng.random()
            if timedelta(days=1) < age < timedelta(days=8) and roll > 0.8:
                continue  # Restée sans devis : alerte « demande sans réponse ».
            if roll > 0.88:
                at = t0 + timedelta(hours=rng.uniform(2, 30))
                services.cancel(client, req)
                RequestEvent.objects.filter(request=req, status="cancelled").update(created_at=at)
                ServiceRequest.objects.filter(pk=req.pk).update(updated_at=at)
                continue

            quotes = []
            t = t0
            for pro in rng.sample(by_trade[slug], k=len(by_trade[slug])):
                t += timedelta(hours=rng.uniform(0.3, 9))
                if t > now:
                    break
                amount = max(2000, round(base * rng.uniform(0.8, 1.35) / 500) * 500)
                quote = services.submit_quote(pro, req, amount, "Devis tout compris.")
                Quote.objects.filter(pk=quote.pk).update(created_at=t)
                quotes.append(quote)
            booked_at = t + timedelta(hours=rng.uniform(1, 20))
            if not quotes or booked_at > now or roll > 0.82:
                continue  # Devis reçus, client pas encore décidé.

            quote = min(quotes, key=lambda q: q.amount) if rng.random() < 0.6 else quotes[0]
            services.accept_quote(client, req, quote.pk)
            RequestEvent.objects.filter(request=req, status="booked").update(created_at=booked_at)
            done_at = booked_at + timedelta(days=rng.uniform(0.5, 4))
            if done_at > now - hour:
                ServiceRequest.objects.filter(pk=req.pk).update(updated_at=booked_at)
                continue  # Mission en cours.

            services.complete(rng.choice([client, quote.pro]), req)
            RequestEvent.objects.filter(request=req, status="done").update(created_at=done_at)
            ServiceRequest.objects.filter(pk=req.pk).update(updated_at=done_at)
            reviewed_at = done_at + timedelta(hours=rng.uniform(2, 30))
            if reviewed_at > now or rng.random() < 0.25:
                continue
            rating = rng.choices([5, 4, 3, 2, 1], [55, 30, 8, 5, 2])[0]
            review = services.leave_review(client, req, rating, rng.choice(COMMENTS[rating]))
            Review.objects.filter(pk=review.pk).update(created_at=reviewed_at)
