// Données du cadre du site public (pied de page, 404, erreur) : les métiers, depuis le cache de
// `publicApi()`. Une panne donne une liste vide, jamais une erreur : le cadre s'affiche toujours.
import "server-only";

import { catalogTradesList } from "@jeflink/api-client";

import { localized } from "@/lib/requests/catalog";
import { publicApi } from "@/lib/public-api";

export type ShellTrade = { slug: string; name: string };

export async function loadShellTrades(locale: string): Promise<ShellTrade[]> {
  try {
    const response = await catalogTradesList(publicApi().options);
    return response.data.map((trade) => ({
      slug: trade.slug,
      name: localized(trade.name, locale),
    }));
  } catch {
    return [];
  }
}
