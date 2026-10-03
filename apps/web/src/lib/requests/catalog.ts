// Catalogue de l'API vers les options du formulaire (spec 003, web 1). Métiers et zones sont des
// données : rien n'est listé en dur. Un libellé wolof absent retombe sur le français (ADR 0009).
import type { LocalizedText, TradeDetail, Zone } from "@jeflink/api-client";

import type { Draft } from "./draft.ts";
import type { TradeOption, ZoneOption } from "./search.ts";

export function localized(text: Pick<LocalizedText, "fr" | "wo">, locale: string): string {
  return (locale === "wo" && text.wo ? text.wo : text.fr).trim();
}

export function toTradeOptions(details: readonly TradeDetail[], locale: string): TradeOption[] {
  return details.map((trade) => ({
    slug: trade.slug,
    name: localized(trade.name, locale),
    aliases: trade.aliases,
    services: trade.services.map((service) => ({
      slug: service.slug,
      name: localized(service.name, locale),
      aliases: service.aliases,
      urgent: service.urgent,
    })),
  }));
}

export function toZoneOptions(zones: readonly Zone[]): ZoneOption[] {
  return zones.map((zone) => ({
    slug: zone.slug,
    name: zone.name,
    city: zone.city,
    aliases: zone.aliases,
  }));
}

/**
 * Brouillon relu après un temps : un métier, un service ou un quartier que le catalogue ne
 * connaît plus (retiré par l'Ops) est vidé, jamais envoyé.
 */
export function reconcileDraft(
  draft: Draft,
  trades: readonly TradeOption[],
  zones: readonly ZoneOption[],
): Draft {
  const trade = trades.find((item) => item.slug === draft.tradeSlug);
  const serviceKnown = trade?.services.some((service) => service.slug === draft.serviceSlug);
  const zoneKnown = zones.some((zone) => zone.slug === draft.zoneSlug);
  return {
    ...draft,
    tradeSlug: trade ? draft.tradeSlug : "",
    serviceSlug: trade && serviceKnown ? draft.serviceSlug : "",
    zoneSlug: zoneKnown ? draft.zoneSlug : "",
  };
}
