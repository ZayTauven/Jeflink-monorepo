// Validation du formulaire et corps du POST (spec 003, web 1). La même fonction sert au
// navigateur (messages au bon endroit) et à la Server Action (on ne fait confiance à personne).
import type { RequestCreateRequest } from "@jeflink/api-client";

import type { Draft } from "./draft.ts";

export type Location = { lat: number; lon: number };

export type FieldKey = "trade" | "zone" | "landmark" | "description" | "date" | "displayName";

/** Valeur : clé sous `requests.form.errors`. */
export type FieldErrors = Partial<Record<FieldKey, string>>;

export const MIN_TEXT = 3;
export const MAX_LANDMARK = 300;
export const MAX_DESCRIPTION = 1000;
export const MAX_ZONE_TEXT = 80;

export function isLocation(value: unknown): value is Location {
  if (typeof value !== "object" || value === null) return false;
  const { lat, lon } = value as Record<string, unknown>;
  return (
    typeof lat === "number" &&
    typeof lon === "number" &&
    Number.isFinite(lat) &&
    Number.isFinite(lon) &&
    lat >= -90 &&
    lat <= 90 &&
    lon >= -180 &&
    lon <= 180
  );
}

/**
 * Obligatoires : métier, quartier, et repère ou position. Description facultative si un service
 * est choisi, sinon 3 caractères au moins. `today` : `AAAA-MM-JJ` à Dakar.
 */
export function validateDraft(
  draft: Draft,
  options: { hasLocation: boolean; profileComplete: boolean; today: string },
): FieldErrors {
  const errors: FieldErrors = {};
  if (!draft.tradeSlug) errors.trade = "trade";
  if (draft.otherZone ? draft.zoneText.trim().length < 2 : !draft.zoneSlug) errors.zone = "zone";
  if (!options.hasLocation && draft.landmark.trim().length < MIN_TEXT) errors.landmark = "landmark";
  if (!draft.serviceSlug && draft.description.trim().length < MIN_TEXT) {
    errors.description = "description";
  }
  if (draft.when === "date" && (!draft.date || draft.date < options.today)) errors.date = "date";
  if (!options.profileComplete && !draft.displayName.trim()) errors.displayName = "displayName";
  return errors;
}

export function hasErrors(errors: FieldErrors): boolean {
  return Object.keys(errors).length > 0;
}

/** Corps de `requests_create`. La position n'y entre que si elle est donnée, et nulle part ailleurs. */
export function buildRequestBody(draft: Draft, location?: Location | null): RequestCreateRequest {
  const body: RequestCreateRequest = {
    trade_slug: draft.tradeSlug,
    landmark: draft.landmark.trim().slice(0, MAX_LANDMARK),
    description: draft.description.trim().slice(0, MAX_DESCRIPTION),
    preferred_when: draft.when,
    preferred_period: draft.when === "date" ? draft.period : "any",
  };
  if (draft.serviceSlug) body.service_slug = draft.serviceSlug;
  if (draft.otherZone) body.zone_text = draft.zoneText.trim().slice(0, MAX_ZONE_TEXT);
  else if (draft.zoneSlug) body.zone_slug = draft.zoneSlug;
  if (draft.urgent) body.urgent = true;
  if (draft.when === "date") body.preferred_date = draft.date;
  if (location && isLocation(location)) body.location = { lat: location.lat, lon: location.lon };
  return body;
}

/** Après `zone_ambiguous` : le quartier choisi remplace le texte libre ; la clé reste. */
export function withZoneChoice(draft: Draft, slug: string): Draft {
  return { ...draft, otherZone: false, zoneSlug: slug, zoneText: "" };
}
