"""Mode guidé de Jef, sans clé d'API : questions fixes par métier et fiche composée à la main.

Jef reste utile sans IA : le client répond à quelques questions à choix, le pro reçoit une fiche
ordonnée. Les questions servent d'abord à la sécurité, puis au diagnostic (« les voisins ont-ils du
courant ? »), puis au devis (appareil, étage, matériel). Le mode IA (ai.py) produit la même fiche.
"""

import re
import unicodedata

Q = list[dict]
NO_IDEA = "Je ne sais pas"


def _q(qid: str, question: str, *choices: str, urgent: tuple[str, ...] = ()) -> dict:
    """Question à choix (aucun choix = réponse libre). `urgent` : réponses qui rendent urgent."""
    q = {"id": qid, "question": question, "choices": list(choices)}
    if urgent:
        q["urgent"] = list(urgent)
    return q


FLOOR = _q("q9", "À quel étage ?", "Rez-de-chaussée", "1er ou 2e étage", "3e étage ou plus")

QUESTIONS: dict[str, Q] = {
    "plomberie": [
        _q(
            "q1",
            "Que se passe-t-il ?",
            "Fuite d'eau",
            "C'est bouché ou ça déborde",
            "Pas d'eau ou peu de pression",
            "Pas d'eau chaude",
            "Installer ou changer (robinet, WC…)",
        ),
        _q(
            "q2",
            "Où ?",
            "Cuisine",
            "Salle de bain ou WC",
            "Chauffe-eau",
            "Citerne, pompe ou surpresseur",
            "Mur, toit ou plafond",
        ),
        _q(
            "q3",
            "Est-ce que ça s'aggrave ?",
            "Oui, ça coule beaucoup ou ça déborde",
            "Non, c'est stable",
            NO_IDEA,
            urgent=("Oui, ça coule beaucoup ou ça déborde",),
        ),
        FLOOR,
    ],
    "electricite": [
        _q(
            "q1",
            "Qu'est-ce qui ne marche pas ?",
            "Plus de courant dans toute la maison",
            "Une pièce",
            "Une prise, une lampe ou un interrupteur",
            "Le disjoncteur saute",
            "Installer (prises, lampes, ventilateur)",
        ),
        _q(
            "q2",
            "Ça chauffe, ça sent le brûlé ou il y a des étincelles ?",
            "Oui",
            "Non",
            urgent=("Oui",),
        ),
        _q("q3", "Les voisins ont-ils du courant ?", "Oui", "Non", NO_IDEA),
        FLOOR,
    ],
    "climatisation": [
        _q(
            "q1",
            "Quel est le souci ?",
            "Ne refroidit plus",
            "Ne s'allume pas",
            "Coule à l'intérieur",
            "Fait du bruit ou sent mauvais",
            "Installer un appareil neuf",
            "Nettoyage ou entretien",
        ),
        _q("q2", "Quel appareil ?", "Split mural", "Clim fenêtre", "Armoire (colonne)", NO_IDEA),
        _q("q3", "Combien d'appareils ?", "1 appareil", "2 appareils", "3 appareils ou plus"),
        _q(
            "q4",
            "Le bloc extérieur est-il facile d'accès ?",
            "Oui, au sol ou sur un balcon",
            "En hauteur, il faut une échelle",
            NO_IDEA,
        ),
    ],
    "electromenager": [
        _q(
            "q1",
            "Quel appareil ?",
            "Réfrigérateur ou congélateur",
            "Machine à laver",
            "Cuisinière ou four",
            "Télévision",
            "Micro-ondes ou petit appareil",
        ),
        _q(
            "q2",
            "Que se passe-t-il ?",
            "Ne s'allume pas",
            "Ne refroidit plus ou ne chauffe plus",
            "Fuit",
            "Fait du bruit",
            "Autre panne",
        ),
        _q(
            "q3",
            "Quelle marque ?",
            "Samsung",
            "LG",
            "Hisense",
            "Midea",
            "Nasco",
            "Autre ou je ne sais pas",
        ),
    ],
    "menage": [
        _q(
            "q1",
            "Quel type de ménage ?",
            "Ménage courant",
            "Grand ménage",
            "Après travaux",
            "Lessive ou repassage",
            "Canapé, matelas ou tapis",
        ),
        _q(
            "q2",
            "Quelle taille de logement ?",
            "Studio",
            "Chambre-salon",
            "2 chambres et salon",
            "Villa ou étage entier",
        ),
        _q("q3", "Produits et matériel fournis ?", "Oui", "Non, à apporter", "En partie"),
        _q(
            "q4",
            "À quelle fréquence ?",
            "Une seule fois",
            "Chaque semaine",
            "Plusieurs fois par semaine",
        ),
    ],
    "petits-travaux": [
        _q(
            "q1",
            "Quel travail ?",
            "Monter un meuble",
            "Fixer (étagère, télé, rideau)",
            "Porte ou serrure",
            "Peinture",
            "Carrelage ou petite maçonnerie",
        ),
        _q("q2", "Le matériel est-il déjà acheté ?", "Oui", "Non, à prévoir", "En partie"),
        _q("q3", "Combien d'éléments ?", "Un seul", "2 ou 3", "4 ou plus"),
        FLOOR,
    ],
}
GENERIC: Q = [
    _q("q1", "Depuis quand ?", "Aujourd'hui", "Quelques jours", "Plus d'une semaine"),
    _q(
        "q2",
        "Est-ce que ça s'aggrave ?",
        "Oui",
        "Non",
        NO_IDEA,
        urgent=("Oui",),
    ),
    FLOOR,
]

# Fiche du pro : chaque question a un libellé court, et certaines réponses sont reformulées
# en fait (une réponse « Oui » ne dit rien sans sa question). None = réponse non reprise.
# Les réponses « Je ne sais pas » ne sont jamais reprises.
Fact = tuple[str, dict[str, str | None]]
FACTS: dict[str, dict[str, Fact]] = {
    "plomberie": {
        "q1": ("Problème", {}),
        "q2": ("Endroit", {}),
        "q3": (
            "Évolution",
            {
                "Oui, ça coule beaucoup ou ça déborde": "S'aggrave (coule beaucoup ou déborde)",
                "Non, c'est stable": "Stable",
            },
        ),
    },
    "electricite": {
        "q1": ("Panne", {}),
        "q2": (
            "Signes de danger",
            {
                "Oui": "Chaleur, odeur de brûlé ou étincelles",
                "Non": "Aucun (ni chaleur, ni odeur, ni étincelles)",
            },
        ),
        "q3": (
            "Voisins",
            {
                "Oui": "Ont du courant (panne propre au logement)",
                "Non": "Sans courant aussi (coupure du quartier probable)",
            },
        ),
    },
    "climatisation": {
        "q1": ("Souci", {}),
        "q2": ("Appareil", {}),
        "q3": ("Nombre", {}),
        "q4": (
            "Bloc extérieur",
            {
                "Oui, au sol ou sur un balcon": "Facile d'accès (sol ou balcon)",
                "En hauteur, il faut une échelle": "En hauteur (prévoir une échelle)",
            },
        ),
    },
    "electromenager": {
        "q1": ("Appareil", {}),
        "q2": ("Panne", {}),
        "q3": ("Marque", {"Autre ou je ne sais pas": None}),
    },
    "menage": {
        "q1": ("Prestation", {}),
        "q2": ("Logement", {}),
        "q3": (
            "Produits et matériel",
            {
                "Oui": "Fournis par le client",
                "Non, à apporter": "À apporter",
                "En partie": "En partie fournis",
            },
        ),
        "q4": ("Fréquence", {}),
    },
    "petits-travaux": {
        "q1": ("Travail", {}),
        "q2": (
            "Matériel",
            {"Oui": "Déjà acheté", "Non, à prévoir": "À prévoir", "En partie": "En partie acheté"},
        ),
        "q3": ("Quantité", {}),
    },
    "": {  # questions génériques (métier sans questions propres)
        "q1": ("Depuis", {}),
        "q2": ("Évolution", {"Oui": "S'aggrave", "Non": "Stable"}),
    },
}
COMMON_FACTS: dict[str, Fact] = {"q9": ("Étage", {})}


def fact(trade_slug: str, qid: str, answer: str) -> tuple[str, str] | None:
    """(libellé, valeur) d'une réponse pour la fiche du pro, ou None si elle n'apprend rien."""
    if not answer or answer == NO_IDEA:
        return None
    facts = FACTS.get(trade_slug if trade_slug in QUESTIONS else "", {})
    label, say = facts.get(qid) or COMMON_FACTS.get(qid) or ("Précision", {})
    value = say.get(answer, answer)
    return None if value is None else (label, value)


def fact_line(label: str, value: str) -> str:
    return f"{label} : {value}"


# Mots et radicaux (texte sans accents ni majuscules), avec un poids : 3 = mot qui désigne le
# métier à coup sûr, 1 = indice. Les mots wolof courants sont repris tels qu'on les écrit.
KEYWORDS: dict[str, dict[str, int]] = {
    "plomberie": {
        "robinet": 3,
        "fuit": 2,
        "fuite d'eau": 3,
        "fuite": 1,
        "coul": 1,
        "goutte": 1,
        "evier": 3,
        "lavabo": 3,
        "wc": 3,
        "toilette": 3,
        "chasse": 2,
        "douche": 3,
        "tuyau": 2,
        "bouch": 2,
        "deborde": 2,
        "inond": 2,
        "canalisation": 3,
        "egout": 3,
        "fosse": 3,
        "chauffe-eau": 3,
        "cumulus": 3,
        "ballon": 1,
        "citerne": 3,
        "surpresseur": 3,
        "pompe": 2,
        "flotteur": 3,
        "sen'eau": 3,
        "seneau": 3,
        "sde": 2,
        "ndox": 3,
        "eau": 1,
    },
    "electricite": {
        "courant": 2,
        "kourant": 3,
        "electricit": 3,
        "electrique": 2,
        "prise": 2,
        "disjoncteur": 3,
        "fusible": 3,
        "plombs": 2,
        "tableau": 1,
        "lumiere": 2,
        "lampe": 2,
        "ampoule": 3,
        "neon": 3,
        "interrupteur": 3,
        "compteur": 1,
        "woyofal": 3,
        "senelec": 3,
        "coupure": 1,
        "court-circuit": 3,
        "etincelle": 2,
        "dagg": 2,
        "onduleur": 3,
        "groupe electrogene": 3,
        "ventilateur": 1,
    },
    "climatisation": {
        "clim": 3,
        "climatis": 3,
        "climatiseur": 3,
        "clime": 3,
        "split": 3,
        "btu": 3,
        "froid": 1,
    },
    "electromenager": {
        "frigo": 3,
        "frigidaire": 3,
        "refrigerateur": 3,
        "congel": 3,
        "machine a laver": 3,
        "lave-linge": 3,
        "lave linge": 3,
        "four": 2,
        "micro-onde": 3,
        "cuisiniere": 3,
        "plaque": 1,
        "television": 3,
        "tele": 2,
        "fer a repasser": 3,
    },
    "menage": {
        "menage": 3,
        "nettoy": 3,
        "repassage": 3,
        "lessive": 3,
        "linge": 2,
        "vitres": 2,
        "poussiere": 2,
        "canape": 2,
        "matelas": 2,
        "tapis": 2,
    },
    "petits-travaux": {
        "peinture": 3,
        "peindre": 3,
        "meuble": 2,
        "etagere": 3,
        "montage": 2,
        "monter": 1,
        "fixer": 2,
        "tringle": 3,
        "rideau": 2,
        "serrure": 3,
        "porte": 1,
        "carrelage": 3,
        "maconnerie": 3,
    },
}

# Situations dangereuses (texte sans accents). « gaz » seul n'en fait pas partie : « recharge de
# gaz » est la demande la plus courante pour une clim.
DANGER = (
    "fuite de gaz",
    "odeur de gaz",
    "sent le gaz",
    "ca sent le gaz",
    "etincelle",
    "brule",
    "fume",
    "fumee",
    "feu",
    "flamme",
    "electrocut",
    "decharge",
    "ca chauffe",
    "prise chauffe",
    "cable chauffe",
    "inond",
    "eau dans le tableau",
    "tableau mouille",
    "prise mouillee",
)
GAS = ("fuite de gaz", "odeur de gaz", "sent le gaz", "ca sent le gaz")
FIRE_TIP = (
    "S'il y a de la fumée, une odeur de brûlé ou des étincelles : coupez le disjoncteur général, "
    "ne touchez à rien et sortez si ça brûle. Pompiers : 18."
)
GAS_TIP = (
    "Odeur de gaz : fermez la bouteille, ouvrez les fenêtres, n'allumez rien et sortez si "
    "l'odeur est forte. Pompiers : 18."
)


def plain(text: str) -> str:
    """Minuscules sans accents, apostrophes droites, pour comparer des mots."""
    text = unicodedata.normalize("NFD", text.lower().replace("’", "'"))
    return "".join(c for c in text if unicodedata.category(c) != "Mn")


def _has(words: str, key: str) -> bool:
    """Mot présent : radical (5 lettres et plus, « bouch » → bouché) ou mot entier (« four »)."""
    tail = "" if len(key) >= 5 else r"[sx]?\b"
    return re.search(rf"\b{re.escape(key)}{tail}", words) is not None


def guess_trade(text: str, slugs: list[str]) -> str:
    """Métier le plus probable d'après les mots du client ; en cas d'égalité, on ne devine pas."""
    words = plain(text)
    scores = {
        slug: sum(w for key, w in KEYWORDS.get(slug, {}).items() if _has(words, key))
        for slug in slugs
    }
    ranked = sorted(scores.values(), reverse=True)
    if not ranked or ranked[0] == 0 or (len(ranked) > 1 and ranked[0] == ranked[1]):
        return ""
    return max(scores, key=scores.get)


def danger(text: str) -> bool:
    """Le texte décrit-il un danger (feu, gaz, électricité, inondation) ? « pas urgent » non."""
    words = plain(text)
    if any(_has(words, d) for d in DANGER):
        return True
    return re.search(r"(?<!pas )\burgent", words) is not None


FIRE = ("etincelle", "brule", "fume", "feu", "flamme", "chauffe", "electrocut", "decharge")
WATER_TIP = (
    "Fermez le robinet d'arrêt (sous l'évier ou près du compteur d'eau). Si l'eau touche des "
    "prises, coupez le courant au disjoncteur sans marcher dans l'eau."
)


def safety_tips(text: str, trade_slug: str = "") -> list[str]:
    """Gestes de sécurité à montrer tout de suite, avant les questions (vide sans danger)."""
    words = plain(text)
    if not danger(text):
        return []
    tips = []
    if any(g in words for g in GAS):
        tips.append(GAS_TIP)
    if any(_has(words, f) for f in FIRE if f != "chauffe") or (
        "chauffe" in words and "chauffe-eau" not in words
    ):
        tips.append(FIRE_TIP)
    if trade_slug == "plomberie" or any(_has(words, w) for w in ("inond", "deborde")):
        tips.append(WATER_TIP)
    return tips


def questions(trade_slug: str) -> Q:
    return QUESTIONS.get(trade_slug, GENERIC)


def _title(text: str) -> str:
    first = re.split(r"(?<=[.!?])\s|\n", text.strip(), maxsplit=1)[0].strip(" .")
    first = first[:1].upper() + first[1:]
    if len(first) <= 80:
        return first
    # Trop long : on garde la première proposition (« …depuis hier, elle fait du bruit »).
    clause = first[:80].rsplit(",", 1)[0].strip()
    return clause if len(clause) >= 20 else first[:79].rsplit(" ", 1)[0] + "…"


def _tips(trade_slug: str, a: dict, text: str) -> list[str]:
    """Conseils adaptés aux réponses : seulement des gestes sûrs, jamais une réparation."""
    q1 = a.get("q1", "")
    tips = safety_tips(text, trade_slug)
    if trade_slug == "plomberie":
        if q1.startswith(("Fuite", "C'est bouché")) and not tips:
            tips.append(
                "Si l'eau coule encore, fermez le robinet d'arrêt (sous l'évier ou près du "
                "compteur d'eau)."
            )
        if q1.startswith("Pas d'eau"):
            tips.append(
                "Demandez aux voisins s'ils ont de l'eau : sinon, c'est sans doute une coupure "
                "Sen'Eau, pas une panne chez vous."
            )
    elif trade_slug == "electricite":
        if a.get("q3") == "Non" or q1.startswith("Plus de courant"):
            tips.append(
                "Si les voisins n'ont pas de courant non plus, c'est sans doute une coupure "
                "Senelec. Avec un compteur Woyofal, vérifiez aussi le crédit."
            )
        tips.append(
            "Ne remettez pas le disjoncteur s'il saute encore, et ne touchez rien avec les mains "
            "mouillées."
        )
    elif trade_slug == "climatisation":
        tips.append("Éteignez la clim si elle coule ou fait un bruit anormal.")
        tips.append("Notez la marque écrite sur l'appareil pour la donner au pro.")
    elif trade_slug == "electromenager":
        if q1.startswith("Réfrigérateur"):
            tips.append("Ouvrez le frigo le moins possible pour garder le froid.")
        elif q1.startswith("Cuisinière"):
            tips.append("Cuisinière à gaz : fermez la bouteille en attendant le pro.")
        else:
            tips.append("Débranchez l'appareil en attendant le pro.")
    elif trade_slug == "menage":
        tips.append("Rangez les objets fragiles ou de valeur avant le passage.")
    elif trade_slug == "petits-travaux":
        tips.append("Si possible, prenez les mesures de l'endroit.")
    return tips[:3]


def _bring(trade_slug: str, a: dict) -> list[str]:
    """Matériel à prévoir selon les réponses : une suggestion, que le pro confirme sur place."""
    q1, q2 = a.get("q1", ""), a.get("q2", "")
    if trade_slug == "plomberie":
        if q1.startswith("C'est bouché"):
            return ["Furet ou déboucheur", "Ventouse"]
        if q1.startswith("Pas d'eau chaude") or q2 == "Chauffe-eau":
            return ["Testeur", "Résistance et thermostat de chauffe-eau"]
        if q2.startswith("Citerne"):
            return ["Pièces de pompe ou de surpresseur", "Flotteur"]
        return ["Joints et flexibles", "Raccords courants"]
    if trade_slug == "electricite":
        if q1.startswith("Le disjoncteur") or a.get("q2") == "Oui":
            return ["Testeur de tension", "Disjoncteurs et prises de rechange"]
        if q1.startswith("Une prise"):
            return ["Ampoules, douilles et prises", "Dominos"]
        return ["Testeur de tension", "Câble et dominos"]
    if trade_slug == "climatisation":
        if q1.startswith("Installer"):
            return ["Tuyau cuivre et support", "Échelle"]
        if q1.startswith("Coule"):
            return ["Kit de nettoyage", "Tuyau d'évacuation ou pompe de relevage"]
        if q1.startswith("Nettoyage"):
            return ["Kit de nettoyage"]
        bring = ["Manomètres et gaz"]
        return bring + (["Échelle"] if a.get("q4", "").startswith("En hauteur") else [])
    if trade_slug == "electromenager":
        return ["Multimètre", "Pièces courantes de la marque indiquée"]
    if trade_slug == "menage":
        return ["Produits et matériel"] if a.get("q3", "").startswith(("Non", "En partie")) else []
    if trade_slug == "petits-travaux":
        if a.get("q2", "").startswith(("Non", "En partie")):
            return ["Matériel à acheter avec le client", "Perceuse et chevilles"]
        return ["Perceuse et chevilles", "Niveau et mètre"]
    return []


def brief(text: str, trade_slug: str, trade_name: str, qs: Q, answers: dict) -> dict:
    """Fiche du mode guidé : le texte du client, ses réponses interprétées (« Endroit : cuisine »,
    jamais « question réponse »), conseils et matériel adaptés. Même format que le mode IA."""
    facts = [f for q in qs if (f := fact(trade_slug, q["id"], answers.get(q["id"], "")))]
    lines = [fact_line(label, value) for label, value in facts]
    urgent = danger(text) or any(answers.get(q["id"]) in q.get("urgent", ()) for q in qs)
    # La description reste les mots du client ; les faits vont dans la fiche du pro (pas de
    # doublon). En mode IA, la description intègre les réponses en phrases.
    description = text.strip()
    return {
        "title": _title(text),
        "description": description,
        "urgent": urgent,
        "client_tips": _tips(trade_slug, answers, text),
        # Résumé : les deux premiers faits (souvent le problème et l'endroit).
        "pro_summary": " · ".join(value for _, value in facts[:2]),
        "pro_details": lines,
        "pro_bring": _bring(trade_slug, answers),
    }
