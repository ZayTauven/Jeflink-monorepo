"""Métiers et services de départ (spec 002, Q1 à Q3), chargés par ``seed_reference_data``.

Seul endroit du code où des métiers sont écrits en dur : ensuite, l'Ops les gère dans l'admin.
Libellés ``wo`` vides (aucune traduction figée sans locuteur), prix vides (Q3).
"""

from typing import TypedDict


class ServiceData(TypedDict, total=False):
    slug: str
    name_fr: str
    aliases: list[str]
    urgent: bool


class TradeData(TypedDict, total=False):
    slug: str
    name_fr: str
    short_description_fr: str
    seo_title_fr: str
    aliases: list[str]
    icon_key: str
    services: list[ServiceData]


TRADES: list[TradeData] = [
    {
        "slug": "plombier",
        "name_fr": "Plomberie",
        "short_description_fr": (
            "Fuites, débouchage, chasse d'eau, chauffe-eau, pompes et sanitaires."
        ),
        "aliases": ["plombier", "WC qui coule", "chasse", "fuite"],
        "icon_key": "plumbing",
        "services": [
            {
                "slug": "fuite-robinetterie",
                "name_fr": "Fuite et robinetterie",
                "aliases": ["fuite d'eau", "robinet"],
                "urgent": True,
            },
            {
                "slug": "debouchage",
                "name_fr": "Débouchage (évier, WC, douche)",
                "aliases": ["évier bouché", "WC bouché"],
            },
            {"slug": "chasse-d-eau", "name_fr": "Chasse d'eau", "aliases": ["WC qui coule"]},
            {"slug": "chauffe-eau", "name_fr": "Chauffe-eau"},
            {"slug": "pompe-surpresseur", "name_fr": "Pompe et surpresseur", "aliases": ["pompe"]},
            {"slug": "pose-sanitaires", "name_fr": "Pose de sanitaires", "aliases": ["lavabo"]},
        ],
    },
    {
        "slug": "electricien",
        "name_fr": "Électricité",
        "short_description_fr": "Pannes, prises, éclairage, tableau électrique et raccordements.",
        "aliases": [
            "électricien",
            "tableau électrique",
            "disjoncteur",
            "compteur",
            "coupure de courant",
        ],
        "icon_key": "electricity",
        "services": [
            {
                "slug": "panne-courant",
                "name_fr": "Panne et coupure de courant",
                "aliases": ["plus de courant", "coupure"],
                "urgent": True,
            },
            {"slug": "prises-interrupteurs", "name_fr": "Prises et interrupteurs"},
            {"slug": "eclairage", "name_fr": "Éclairage", "aliases": ["lampe", "ampoule"]},
            {
                "slug": "tableau-electrique",
                "name_fr": "Tableau électrique et disjoncteur",
                "aliases": ["disjoncteur"],
            },
            {"slug": "ventilateur-plafond", "name_fr": "Ventilateur de plafond"},
            {"slug": "raccordement", "name_fr": "Raccordement", "aliases": ["compteur"]},
        ],
    },
    {
        "slug": "climatisation",
        "name_fr": "Froid et climatisation",
        "short_description_fr": (
            "Entretien et panne de clim, recharge de gaz, frigos et congélateurs."
        ),
        "aliases": ["frigoriste", "clim", "climatiseur", "frigo"],
        "icon_key": "cooling",
        "services": [
            {
                "slug": "entretien-clim",
                "name_fr": "Entretien de clim",
                "aliases": ["nettoyage clim"],
            },
            {"slug": "panne-clim", "name_fr": "Panne de clim"},
            {"slug": "recharge-gaz", "name_fr": "Recharge de gaz"},
            {"slug": "pose-split", "name_fr": "Pose de split", "aliases": ["installation clim"]},
            {
                "slug": "frigo-congelateur",
                "name_fr": "Frigo ou congélateur en panne",
                "aliases": ["frigo", "réfrigérateur", "congélateur"],
                "urgent": True,
            },
        ],
    },
    {
        "slug": "electromenager",
        "name_fr": "Électroménager",
        "short_description_fr": (
            "Machine à laver, cuisinière, four, micro-ondes et petits appareils."
        ),
        "aliases": ["frigo", "machine", "dépannage", "réparateur"],
        "icon_key": "appliance",
        "services": [
            {"slug": "machine-a-laver", "name_fr": "Machine à laver", "aliases": ["machine"]},
            {"slug": "cuisiniere-four", "name_fr": "Cuisinière et four", "aliases": ["gazinière"]},
            {"slug": "micro-ondes", "name_fr": "Micro-ondes"},
            {
                "slug": "petit-electromenager",
                "name_fr": "Petit électroménager",
                "aliases": ["mixeur"],
            },
        ],
    },
    {
        "slug": "menage",
        "name_fr": "Ménage",
        "short_description_fr": "Ménage ponctuel, grand nettoyage, canapés et matelas.",
        "seo_title_fr": "Femme de ménage et nettoyage",
        "aliases": ["femme de ménage", "nettoyage"],
        "icon_key": "cleaning",
        "services": [
            {"slug": "menage-ponctuel", "name_fr": "Ménage ponctuel"},
            {
                "slug": "grand-nettoyage",
                "name_fr": "Grand nettoyage (fin de travaux, déménagement)",
                "aliases": ["fin de chantier"],
            },
            {"slug": "canapes-matelas", "name_fr": "Canapés et matelas"},
        ],
    },
    {
        "slug": "petits-travaux",
        "name_fr": "Petits travaux",
        "short_description_fr": "Peinture, menuiserie, maçonnerie légère, montage et fixations.",
        "aliases": ["bricolage", "bricoleur", "peintre"],
        "icon_key": "handyman",
        "services": [
            {"slug": "peinture", "name_fr": "Peinture", "aliases": ["peintre"]},
            {
                "slug": "menuiserie",
                "name_fr": "Menuiserie (portes, meubles)",
                "aliases": ["menuisier"],
            },
            {
                "slug": "maconnerie-carrelage",
                "name_fr": "Maçonnerie légère et carrelage",
                "aliases": ["maçon", "carreleur"],
            },
            {"slug": "montage-meubles", "name_fr": "Montage de meubles"},
            {
                "slug": "fixations",
                "name_fr": "Fixations (étagères, tringles, TV)",
                "aliases": ["étagère", "tringle"],
            },
        ],
    },
]
