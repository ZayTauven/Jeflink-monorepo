// Listes paginées par curseur (`results`, `next`, `previous`). Les opérations `requests_list` et
// `bookings_list` n'ont pas de type de réponse 200 dans le schéma OpenAPI (point d'API relevé en
// spec 003) : la forme est relue ici, avec méfiance, plutôt que castée à l'aveugle.
import type { ClientBooking, ClientRequest } from "@jeflink/api-client";

export type Page<T> = { results: T[]; next: string | null };

/** Ligne de « Mes demandes » : le résumé du serializer de liste, sans devis ni réservation. */
export type RequestSummary = Pick<
  ClientRequest,
  "public_id" | "status" | "trade" | "service" | "zone" | "urgent" | "created_at" | "expires_at"
>;

export function readPage<T>(data: unknown, accept: (item: unknown) => item is T): Page<T> {
  if (typeof data !== "object" || data === null) return { results: [], next: null };
  const { results, next } = data as { results?: unknown; next?: unknown };
  return {
    results: Array.isArray(results) ? results.filter(accept) : [],
    next: typeof next === "string" && next ? next : null,
  };
}

function hasString(item: unknown, key: string): boolean {
  return (
    typeof item === "object" &&
    item !== null &&
    typeof (item as Record<string, unknown>)[key] === "string"
  );
}

export function isRequestSummary(item: unknown): item is RequestSummary {
  return hasString(item, "public_id") && hasString(item, "status") && hasString(item, "created_at");
}

export function isBooking(item: unknown): item is ClientBooking {
  return (
    hasString(item, "public_id") &&
    hasString(item, "request") &&
    hasString(item, "status") &&
    hasString(item, "cancelled_by") &&
    hasString(item, "created_at")
  );
}
