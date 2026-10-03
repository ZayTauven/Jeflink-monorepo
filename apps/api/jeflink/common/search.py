"""Recherche par les mots des clients (spec 002).

Une seule normalisation pour l'API, l'IA et les fronts.

Le miroir TS (``packages/api-client/src/search/``) passe les mêmes vecteurs
(``common/tests/search_vectors.json``) : toute règle changée ici change là-bas.
"""

import re
import unicodedata
from collections.abc import Iterable

# Ligatures que NFKD ne décompose pas.
_LIGATURES = str.maketrans({"œ": "oe", "Œ": "oe", "æ": "ae", "Æ": "ae", "ß": "ss"})
_NON_ALNUM = re.compile(r"[^a-z0-9]+")

# Sous cette longueur (forme compacte), seule l'égalité compte :
# « PA » ne doit pas trouver « Patte d'Oie ».
MIN_PREFIX_LENGTH = 3

EXACT, TERM_PREFIX, WORD_PREFIX = 0, 1, 2


def normalize(text: str) -> str:
    """Minuscules, sans accents ni ponctuation, espaces fusionnés.

    « Sacré-Cœur » → « sacre coeur ».
    """
    decomposed = unicodedata.normalize("NFKD", text.translate(_LIGATURES))
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return _NON_ALNUM.sub(" ", stripped.lower()).strip()


def clean_aliases(values: Iterable[str]) -> list[str]:
    """Alias saisis : espaces superflus retirés, vides et doublons (selon ``normalize``) écartés."""
    seen: set[str] = set()
    cleaned: list[str] = []
    for value in values:
        text = " ".join(value.split())
        key = normalize(text)
        if key and key not in seen:
            seen.add(key)
            cleaned.append(text)
    return cleaned


def _compact(normalized: str) -> str:
    return normalized.replace(" ", "")


def match(query: str, terms: Iterable[str]) -> int | None:
    """Meilleur rang de ``query`` parmi ``terms``.

    0 égalité, 1 préfixe du terme, 2 préfixe d'un mot.

    ``None`` si aucun terme ne correspond.
    """
    q = normalize(query)
    if not q:
        return None
    q_compact = _compact(q)
    best: int | None = None
    for term in terms:
        t = normalize(term)
        if not t:
            continue
        t_compact = _compact(t)
        if q == t or q_compact == t_compact:
            return EXACT
        if len(q_compact) < MIN_PREFIX_LENGTH:
            continue
        if t.startswith(q) or t_compact.startswith(q_compact):
            rank = TERM_PREFIX
        else:
            words = t.split(" ")
            suffixes = (" ".join(words[i:]) for i in range(1, len(words)))
            if not any(s.startswith(q) for s in suffixes):
                continue
            rank = WORD_PREFIX
        if best is None or rank < best:
            best = rank
    return best
