// Slugs connus du catalogue, vérifiés contre les listes EN CACHE (`getTrades`, `getZones`,
// `getCoverage`), jamais par un appel de détail. Un slug inconnu ou une paire fermée ne coûte donc
// aucun appel à l'API : sinon n'importe qui pourrait épuiser la limite `catalog_read` partagée du
// serveur Next en demandant /xxxx/opengraph-image. Les images Open Graph et la recherche passent
// par ici ; les pages passent par `resolveSlug` (même règle, avec redirection des alias).
import "server-only";

import { getCoverage, getTrades, getZones } from "./data.ts";

/** Slug de métier exactement connu, ou null (alias et inconnus : null, sans appel de détail). */
export async function knownTradeSlug(param: string): Promise<string | null> {
  const trades = await getTrades();
  return trades.some((trade) => trade.slug === param) ? param : null;
}

/** Paire métier × quartier exactement connue ET ouverte (couverture en cache), ou null. */
export async function knownOpenPair(
  tradeParam: string,
  zoneParam: string,
): Promise<{ tradeSlug: string; zoneSlug: string } | null> {
  const [trades, zones, coverage] = await Promise.all([getTrades(), getZones(), getCoverage()]);
  const known =
    trades.some((trade) => trade.slug === tradeParam) &&
    zones.some((zone) => zone.slug === zoneParam);
  if (!known) return null;
  const open = coverage.some((pair) => pair.trade === tradeParam && pair.zone === zoneParam);
  return open ? { tradeSlug: tradeParam, zoneSlug: zoneParam } : null;
}
