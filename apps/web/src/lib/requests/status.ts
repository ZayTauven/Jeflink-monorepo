// Statuts d'une demande et d'une réservation, pour l'affichage (spec 003). Le sens est porté par
// un mot et une icône, jamais par la couleur seule.

export type Tone = "success" | "info" | "warning" | "neutral";

export type RequestState = "needs_zone" | "open" | "quoted" | "booked" | "cancelled" | "expired";

const STATES: readonly string[] = [
  "needs_zone",
  "open",
  "quoted",
  "booked",
  "cancelled",
  "expired",
];

export function requestState(status: string): RequestState | null {
  return STATES.includes(status) ? (status as RequestState) : null;
}

export const STATE_TONE: Record<RequestState, Tone> = {
  needs_zone: "warning",
  open: "info",
  quoted: "info",
  booked: "success",
  cancelled: "neutral",
  expired: "neutral",
};

/** Une demande se retire tant qu'aucune réservation n'est en cours (sinon : annuler la réservation). */
export function canCancelRequest(status: string): boolean {
  return status === "needs_zone" || status === "open" || status === "quoted";
}

export const CLIENT_REASONS = [
  "changed_mind",
  "found_other",
  "price",
  "unavailable",
  "other",
] as const;
export type ClientReason = (typeof CLIENT_REASONS)[number];
export const MAX_NOTE = 200;

export function isClientReason(value: unknown): value is ClientReason {
  return typeof value === "string" && (CLIENT_REASONS as readonly string[]).includes(value);
}

/** `other` exige une note de 200 caractères au plus ; les autres motifs n'en ont pas. */
export function validateCancel(reason: string, note: string): "reason" | "note" | null {
  if (!isClientReason(reason)) return "reason";
  if (reason === "other" && (!note.trim() || note.trim().length > MAX_NOTE)) return "note";
  return null;
}

type BookingLike = {
  request: string;
  status: string;
  cancelled_by: string;
  created_at: string;
};

/**
 * Le pro s'est désisté : une réservation annulée par le pro ou le système, pour cette demande,
 * alors que la demande est revenue à `open` ou `quoted`. La plus récente fait foi.
 */
export function providerWithdrew(
  requestId: string,
  requestStatus: string,
  bookings: readonly BookingLike[],
): boolean {
  if (requestStatus !== "open" && requestStatus !== "quoted") return false;
  const last = bookings
    .filter((booking) => booking.request === requestId && booking.status === "cancelled")
    .sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at))[0];
  return last !== undefined && (last.cancelled_by === "pro" || last.cancelled_by === "system");
}
