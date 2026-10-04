// Recherche par les mots des clients (spec 002), miroir de `jeflink.common.search` (Python).
// Écrit à la main, hors du code généré. Mêmes vecteurs de test que l'API : toute règle changée
// là-bas change ici.

const LIGATURES: Record<string, string> = { œ: "oe", Œ: "oe", æ: "ae", Æ: "ae", ß: "ss" };

/** Sous cette longueur (forme compacte), seule l'égalité compte : « PA » ne trouve pas « Patte d'Oie ». */
export const MIN_PREFIX_LENGTH = 3;

export const MATCH_EXACT = 0;
export const MATCH_TERM_PREFIX = 1;
export const MATCH_WORD_PREFIX = 2;

/** Minuscules, sans accents ni ponctuation, espaces fusionnés : « Sacré-Cœur » → « sacre coeur ». */
export function normalizeSearch(text: string): string {
  return text
    .replace(/[œŒæÆß]/g, (c) => LIGATURES[c] ?? c)
    .normalize("NFKD")
    .replace(/\p{M}/gu, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, " ")
    .trim();
}

const compact = (normalized: string) => normalized.replaceAll(" ", "");

/**
 * Meilleur rang de `query` parmi `terms` (0 égalité, 1 préfixe du terme, 2 préfixe d'un mot),
 * ou `null` si aucun terme ne correspond.
 */
export function matchSearch(query: string, terms: Iterable<string>): number | null {
  const q = normalizeSearch(query);
  if (!q) return null;
  const qCompact = compact(q);
  let best: number | null = null;
  for (const term of terms) {
    const t = normalizeSearch(term);
    if (!t) continue;
    const tCompact = compact(t);
    if (q === t || qCompact === tCompact) return MATCH_EXACT;
    if (qCompact.length < MIN_PREFIX_LENGTH) continue;
    let rank: number;
    if (t.startsWith(q) || tCompact.startsWith(qCompact)) {
      rank = MATCH_TERM_PREFIX;
    } else {
      const words = t.split(" ");
      const hit = words.some((_, i) => i > 0 && words.slice(i).join(" ").startsWith(q));
      if (!hit) continue;
      rank = MATCH_WORD_PREFIX;
    }
    if (best === null || rank < best) best = rank;
  }
  return best;
}
