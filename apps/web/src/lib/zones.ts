import type { Zone } from "./types";

/**
 * Quartiers rangés par ville, dans l'ordre reçu de l'API (déjà triés par ville). Une seule
 * ville ouverte (la démo : Dakar) : le site n'affiche pas de regroupement.
 */
export function zonesByCity(zones: Zone[]): { city: string; zones: Zone[] }[] {
  const groups: { city: string; zones: Zone[] }[] = [];
  for (const zone of zones) {
    const last = groups[groups.length - 1];
    if (last && last.city === zone.city) last.zones.push(zone);
    else groups.push({ city: zone.city, zones: [zone] });
  }
  return groups;
}
