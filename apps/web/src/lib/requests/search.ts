// Recherche locale du métier et du quartier (spec 003, web 1) : hors ligne, sur les mots des
// clients, avec la même règle que l'API (`@jeflink/api-client/search`, spec 002).
import { matchSearch } from "@jeflink/api-client/search";

export type ServiceOption = { slug: string; name: string; aliases: string[]; urgent: boolean };

export type TradeOption = {
  slug: string;
  name: string;
  aliases: string[];
  services: ServiceOption[];
};

export type ZoneOption = { slug: string; name: string; city: string; aliases: string[] };

/**
 * Éléments qui correspondent à `query`, du meilleur rang au moins bon ; à rang égal, l'ordre
 * d'origine (popularité ou position, décidé par l'API). Requête vide : tout, dans l'ordre.
 */
export function rankOptions<T>(
  query: string,
  items: readonly T[],
  terms: (item: T) => string[],
): T[] {
  if (!query.trim()) return [...items];
  const ranked: { item: T; rank: number; index: number }[] = [];
  items.forEach((item, index) => {
    const rank = matchSearch(query, terms(item));
    if (rank !== null) ranked.push({ item, rank, index });
  });
  ranked.sort((a, b) => a.rank - b.rank || a.index - b.index);
  return ranked.map((entry) => entry.item);
}

/** Un métier se trouve par son nom, ses synonymes et les noms de ses services. */
export function searchTrades(query: string, trades: readonly TradeOption[]): TradeOption[] {
  return rankOptions(query, trades, (trade) => [
    trade.name,
    ...trade.aliases,
    ...trade.services.flatMap((service) => [service.name, ...service.aliases]),
  ]);
}

/** Un quartier se trouve par son nom et ses synonymes. */
export function searchZones(query: string, zones: readonly ZoneOption[]): ZoneOption[] {
  return rankOptions(query, zones, (zone) => [zone.name, ...zone.aliases]);
}
