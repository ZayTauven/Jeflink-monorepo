// Résolution d'un segment d'URL en métier ou quartier (spec 006, « Règles d'URL »). Un slug connu
// donne sa page ; un mot ÉGAL à un alias (rang 0 de `matchSearch`) donne une redirection 307 vers
// le slug (les alias sont modifiables par l'Ops, donc jamais un 301) ; tout le reste est inconnu.
// Jamais de redirection sur un préfixe. Les alias n'entrent jamais dans le sitemap. Module pur.
import { MATCH_EXACT, matchSearch } from "@jeflink/api-client/search";

export type Resolvable = { slug: string; aliases: readonly string[]; names?: readonly string[] };

export type Resolution =
  | { kind: "found"; slug: string }
  | { kind: "alias"; slug: string }
  | { kind: "unknown" };

export function resolveSlug(param: string, items: readonly Resolvable[]): Resolution {
  const direct = items.find((item) => item.slug === param);
  if (direct) return { kind: "found", slug: direct.slug };
  // Un slug a la forme canonique (minuscules, tirets) ; le reste n'est pas un alias plausible.
  if (!param || param.length > 60) return { kind: "unknown" };
  const hit = items.find(
    (item) => matchSearch(param, [...item.aliases, ...(item.names ?? [])]) === MATCH_EXACT,
  );
  return hit ? { kind: "alias", slug: hit.slug } : { kind: "unknown" };
}
