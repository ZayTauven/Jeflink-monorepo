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
