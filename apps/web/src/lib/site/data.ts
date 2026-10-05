// Données publiques du site (spec 006) : métiers, quartiers, couverture, statistiques. Tout passe
// par `publicApi()` (GET, cache 5 min, dernière copie en cas de panne). Règle centrale : une panne
// n'est JAMAIS une absence. `null` veut dire « n'existe pas » (404 avec un code d'absence) ; toute
// autre erreur remonte à la page d'erreur (500) ou, pour les chiffres, devient « pas de chiffres ».
import "server-only";

import {
  type CoveragePair,
  type PublicStats,
  type TradeDetail,
  type TradeSummary,
  type Zone,
  type ZoneDetail,
  catalogCoverageList,
  catalogTradeRetrieve,
  catalogTradesList,
  statsRetrieve,
  zoneRetrieve,
  zoneTradesList,
  zonesList,
} from "@jeflink/api-client";

import { isNotFoundError, publicApi } from "@/lib/public-api";

type Reply = { status: number; data: unknown };

/** Corps d'une réponse 200 ; tout autre statut qui arrive ici est une erreur (jamais une absence). */
async function body<T>(reply: Promise<Reply>): Promise<T> {
  const response = await reply;
  if (response.status !== 200) throw new Error(`publicApi : statut ${response.status}`);
  return response.data as T;
}

/** Appel dont une vraie absence (404 avec code d'absence) donne `null`. */
async function orNull<T>(reply: () => Promise<Reply>): Promise<T | null> {
  try {
    return await body<T>(reply());
  } catch (error) {
    if (isNotFoundError(error)) return null;
    throw error;
  }
}

export function getTrades(): Promise<TradeSummary[]> {
  return body(catalogTradesList(publicApi().options));
}

export function getTrade(slug: string): Promise<TradeDetail | null> {
  return orNull(() => catalogTradeRetrieve(slug, publicApi().options));
}

export function getZones(): Promise<Zone[]> {
  return body(zonesList(undefined, publicApi().options));
}

export function getZone(slug: string, trade?: string): Promise<ZoneDetail | null> {
  return orNull(() => zoneRetrieve(slug, trade ? { trade } : undefined, publicApi().options));
}

/** Métiers ouverts dans un quartier. */
export function getZoneTrades(slug: string): Promise<TradeSummary[] | null> {
  return orNull(() => zoneTradesList(slug, publicApi().options));
}

export function getCoverage(): Promise<CoveragePair[]> {
  return body(catalogCoverageList(publicApi().options));
}

/**
 * Chiffres publics, ou null si l'API ne répond pas ou si le filtre est inconnu : le site s'affiche
 * alors avec les chiffres vrais par construction, jamais en erreur à cause des statistiques.
 */
export async function getStats(filter?: {
  trade?: string;
  zone?: string;
}): Promise<PublicStats | null> {
  try {
    const params = filter && (filter.trade || filter.zone) ? filter : undefined;
    return await body<PublicStats>(statsRetrieve(params, publicApi().options));
  } catch {
    return null;
  }
}

/** Même chose pour une liste qui décore une page (métiers de l'accueil) : [] si l'API est en panne. */
export async function softly<T>(load: () => Promise<T[]>): Promise<T[]> {
  try {
    return await load();
  } catch {
    return [];
  }
}
