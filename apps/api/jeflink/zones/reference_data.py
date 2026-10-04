"""Ville et zones de départ (spec 002, Q5), chargées par ``seed_reference_data``.

Cible de lancement : la région de Dakar, Guédiawaye compris. Seul endroit du code où des zones
sont écrites en dur : ensuite, l'Ops les gère dans l'admin. Centres approximatifs relevés sur
OpenStreetMap, à vérifier sur la carte de l'admin. Rayon 1 500 m environ pour un quartier de
Dakar, 3 000 à 5 000 m pour une commune de banlieue. Gorée n'est pas dans le seed V1.
"""

from typing import TypedDict

CITY = {"slug": "dakar", "name": "Dakar"}


class ZoneData(TypedDict, total=False):
    slug: str
    name: str
    aliases: list[str]
    lat: float
    lon: float
    radius_m: int
    position: int


ZONES: list[ZoneData] = [
    {
        "slug": "parcelles-assainies",
        "name": "Parcelles Assainies",
        "aliases": ["Parcelles", "PA", "Unité 15"],
        "lat": 14.7600,
        "lon": -17.4400,
        "radius_m": 2000,
        "position": 1,
    },
    {
        "slug": "pikine",
        "name": "Pikine",
        "aliases": ["Thiaroye", "Dalifort", "Diamaguène", "Mbao"],
        "lat": 14.7550,
        "lon": -17.3900,
        "radius_m": 4000,
        "position": 2,
    },
    {
        "slug": "guediawaye",
        "name": "Guédiawaye",
        "aliases": ["Golf Sud", "Sam Notaire", "Médina Gounass"],
        "lat": 14.7760,
        "lon": -17.3950,
        "radius_m": 3500,
        "position": 3,
    },
    {"slug": "ouakam", "name": "Ouakam", "lat": 14.7240, "lon": -17.4880, "position": 4},
    {"slug": "almadies", "name": "Almadies", "lat": 14.7440, "lon": -17.5180, "radius_m": 1200},
    {"slug": "camberene", "name": "Cambérène", "lat": 14.7660, "lon": -17.4280, "radius_m": 1200},
    {
        "slug": "dieuppeul-derkle",
        "name": "Dieuppeul – Derklé",  # noqa: RUF001 (tiret demi-cadratin voulu)
        "aliases": ["Dieuppeul", "Derklé"],
        "lat": 14.7180,
        "lon": -17.4560,
        "radius_m": 1000,
    },
    {"slug": "fann", "name": "Fann", "lat": 14.6930, "lon": -17.4640, "radius_m": 1200},
    {
        "slug": "fass-colobane",
        "name": "Fass – Colobane",  # noqa: RUF001 (tiret demi-cadratin voulu)
        "aliases": ["Fass", "Colobane"],
        "lat": 14.6860,
        "lon": -17.4520,
        "radius_m": 1000,
    },
    {
        "slug": "grand-dakar",
        "name": "Grand Dakar",
        "lat": 14.7080,
        "lon": -17.4520,
        "radius_m": 1000,
    },
    {"slug": "grand-yoff", "name": "Grand Yoff", "lat": 14.7330, "lon": -17.4540},
    {
        "slug": "hann-bel-air",
        "name": "Hann Bel-Air",
        "aliases": ["Hann", "Bel Air", "Maristes"],
        "lat": 14.7150,
        "lon": -17.4300,
        "radius_m": 2000,
    },
    {
        "slug": "hlm",
        "name": "HLM",
        "aliases": ["HLM Grand Yoff", "HLM Paris"],
        "lat": 14.7080,
        "lon": -17.4430,
        "radius_m": 1000,
    },
    {
        "slug": "keur-massar",
        "name": "Keur Massar",
        "aliases": ["Malika"],
        "lat": 14.7830,
        "lon": -17.3110,
        "radius_m": 3500,
    },
    {
        "slug": "liberte",
        "name": "Liberté",
        "aliases": ["Sicap", "Sicap Liberté", "Sicap Baobab", "Sicap Karack", "Sicap Amitié"],
        "lat": 14.7220,
        "lon": -17.4600,
    },
    {"slug": "medina", "name": "Médina", "lat": 14.6830, "lon": -17.4480, "radius_m": 1000},
    {"slug": "mermoz", "name": "Mermoz", "lat": 14.7080, "lon": -17.4750, "radius_m": 1200},
    {
        "slug": "ngor",
        "name": "Ngor",
        "aliases": ["Ngor Village"],
        "lat": 14.7530,
        "lon": -17.5140,
        "radius_m": 1000,
    },
    {
        "slug": "patte-doie",
        "name": "Patte d'Oie",
        "aliases": ["Patte d'oie", "Patte Doie", "Pattedoie"],
        "lat": 14.7395,
        "lon": -17.4410,
        "radius_m": 1000,
    },
    {
        "slug": "plateau",
        "name": "Plateau",
        "aliases": ["Sandaga", "Dakar centre", "Dakar Plateau"],
        "lat": 14.6680,
        "lon": -17.4370,
    },
    {"slug": "point-e", "name": "Point E", "lat": 14.6960, "lon": -17.4600, "radius_m": 800},
    {"slug": "rufisque", "name": "Rufisque", "lat": 14.7160, "lon": -17.2730, "radius_m": 4000},
    {
        "slug": "sacre-coeur",
        "name": "Sacré-Cœur",
        "aliases": ["Sacré-Cœur 1", "Sacré-Cœur 2", "Sacré-Cœur 3"],
        "lat": 14.7220,
        "lon": -17.4700,
        "radius_m": 1200,
    },
    {
        "slug": "yoff",
        "name": "Yoff",
        "aliases": ["Yoff Layène"],
        "lat": 14.7580,
        "lon": -17.4800,
        "radius_m": 2000,
    },
]
