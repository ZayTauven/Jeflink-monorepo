// Recherche de quartier du site (spec 006, web 8) : la normalisation partagée avec l'API et l'app
// (`matchSearch`), appliquée aux zones en cache. Module pur, testé seul. Le texte tapé n'est ni
// enregistré, ni journalisé, ni recopié ailleurs : il ne sert qu'à choisir une issue.
import { MATCH_EXACT, matchSearch } from "@jeflink/api-client/search";

import { ZONE_QUERY_MAX_LENGTH } from "./zone-query.ts";

export type SearchableZone = { slug: string; name: string; aliases: readonly string[] };

export type SearchOutcome =
  /** Une égalité avec une zone ouverte : redirection (ou choix du métier sans métier). */
  | { kind: "exact"; zone: SearchableZone }
  /** Des préfixes : quartiers proposés, du meilleur au moins bon. */
  | { kind: "suggest"; zones: SearchableZone[] }
  /** Une zone connue où le métier n'est pas ouvert. */
  | { kind: "closed"; zone: SearchableZone }
  /** Rien ne correspond. */
  | { kind: "none" };

/** Texte tapé, borné : trop long ou vide donne une chaîne vide / tronquée, jamais une erreur. */
export function cleanQuery(raw: string | string[] | undefined): string {
  const first = Array.isArray(raw) ? raw[0] : raw;
  return typeof first === "string" ? first.trim().slice(0, ZONE_QUERY_MAX_LENGTH) : "";
}

function ranked(query: string, zones: readonly SearchableZone[]) {
  const hits: { zone: SearchableZone; rank: number; index: number }[] = [];
  zones.forEach((zone, index) => {
    const rank = matchSearch(query, [zone.name, ...zone.aliases]);
    if (rank !== null) hits.push({ zone, rank, index });
  });
  return hits.sort((a, b) => a.rank - b.rank || a.index - b.index);
}

/**
 * Issue d'une recherche. `open` : slugs des zones où le métier est ouvert, ou null sans métier
 * (toutes les zones comptent comme ouvertes).
 */
export function searchZones(
  query: string,
  zones: readonly SearchableZone[],
  open: ReadonlySet<string> | null,
): SearchOutcome {
  if (!query.trim()) return { kind: "none" };
  const hits = ranked(query, zones);
  const isOpen = (zone: SearchableZone) => open === null || open.has(zone.slug);
  const openHits = hits.filter((hit) => isOpen(hit.zone));

  const exact = openHits.find((hit) => hit.rank === MATCH_EXACT);
  if (exact) return { kind: "exact", zone: exact.zone };
  if (openHits.length > 0) return { kind: "suggest", zones: openHits.map((hit) => hit.zone) };

  const closed = hits.find((hit) => !isOpen(hit.zone));
  if (closed) return { kind: "closed", zone: closed.zone };
  return { kind: "none" };
}
