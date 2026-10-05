// Titre « {métier} {locatif} » des pages métier × quartier (spec 006). La grammaire (« à Ouakam »,
// « au Plateau », « aux Almadies ») est une donnée saisie par l'Ops (`Zone.locative_fr`), pas une
// règle en code ; sans elle, le repli est la clé i18n « à {nom} ». Module pur, testé seul.
import type { LocalizedText } from "@jeflink/api-client";

import { localized } from "../requests/catalog.ts";

export type ZoneWording = {
  name: string;
  locative?: Pick<LocalizedText, "fr" | "wo"> | null;
};

/**
 * « à Ouakam », « aux Almadies » : le locatif saisi s'il existe (langue demandée, repli sur le
 * français), sinon le repli de la copie appliqué au nom.
 */
export function zoneLocative(
  zone: ZoneWording,
  fallback: (name: string) => string,
  locale = "fr",
): string {
  const entered = zone.locative ? localized(zone.locative, locale) : "";
  return entered || fallback(zone.name.trim());
}

/** « Plombier à Ouakam » : `seo_title` du métier suivi du locatif du quartier. */
export function tradeZoneTitle(seoTitle: string, where: string): string {
  return `${seoTitle.trim()} ${where}`.trim();
}
