// Pré-remplissage de /demande par l'URL (spec 006, web 9) : `?metier=&quartier=&service=&urgence=1`,
// posé par les boutons du site public. Chaque slug est validé contre le catalogue ; ce que le
// catalogue ne connaît pas est ignoré sans bruit (jamais une erreur, jamais une valeur étrange
// dans le formulaire). Aucune donnée personnelle dans ces paramètres. Modules purs, testés seuls.
import type { Draft } from "./draft.ts";
import type { TradeOption, ZoneOption } from "./search.ts";

export type Prefill = {
  tradeSlug?: string;
  serviceSlug?: string;
  zoneSlug?: string;
  urgent?: true;
};

type Params = Record<string, string | string[] | undefined>;

const SLUG = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;

function single(value: string | string[] | undefined): string | null {
  const first = Array.isArray(value) ? value[0] : value;
  return typeof first === "string" && first.length <= 50 && SLUG.test(first) ? first : null;
}

/** Valeurs de l'URL reconnues par le catalogue : métier, service de ce métier, quartier, urgence. */
export function readPrefill(
  params: Params,
  trades: readonly TradeOption[],
  zones: readonly ZoneOption[],
): Prefill {
  const prefill: Prefill = {};
  const trade = trades.find((item) => item.slug === single(params.metier));
  if (trade) {
    prefill.tradeSlug = trade.slug;
    // Un service n'a de sens qu'avec son propre métier.
    const service = trade.services.find((item) => item.slug === single(params.service));
    if (service) prefill.serviceSlug = service.slug;
  }
  const zone = zones.find((item) => item.slug === single(params.quartier));
  if (zone) prefill.zoneSlug = zone.slug;
  const urgence = Array.isArray(params.urgence) ? params.urgence[0] : params.urgence;
  if (urgence === "1") prefill.urgent = true;
  return prefill;
}

export function hasPrefill(prefill: Prefill): boolean {
  return Object.keys(prefill).length > 0;
}

/**
 * L'URL gagne sur le brouillon pour le métier, le quartier et l'urgence. Le service est vidé si le
 * métier change (un service d'un autre métier serait refusé) ; il est repris de l'URL s'il y est.
 * Tout le reste du brouillon (description, repère, date…) reste tel quel.
 */
export function applyPrefill(draft: Draft, prefill: Prefill): Draft {
  if (!hasPrefill(prefill)) return draft;
  const next: Draft = { ...draft };
  if (prefill.tradeSlug !== undefined) {
    if (prefill.tradeSlug !== draft.tradeSlug) next.serviceSlug = "";
    next.tradeSlug = prefill.tradeSlug;
  }
  if (prefill.serviceSlug !== undefined) next.serviceSlug = prefill.serviceSlug;
  if (prefill.zoneSlug !== undefined) {
    next.zoneSlug = prefill.zoneSlug;
    next.otherZone = false;
    next.zoneText = "";
  }
  if (prefill.urgent) next.urgent = true;
  return next;
}
