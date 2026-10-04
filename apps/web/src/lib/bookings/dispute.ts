// Contestation d'une mission terminée (spec 004, web 3) : motif, texte, fenêtre jusqu'à une heure
// de Dakar. Modules purs.

export const DISPUTE_REASONS = [
  "not_done",
  "poor_quality",
  "damage",
  "price",
  "behaviour",
  "other",
] as const;
export type DisputeReason = (typeof DISPUTE_REASONS)[number];
export const DISPUTE_MIN = 10;
export const DISPUTE_MAX = 1000;

export function isDisputeReason(value: unknown): value is DisputeReason {
  return typeof value === "string" && (DISPUTE_REASONS as readonly string[]).includes(value);
}

/** Motif de la liste fermée et texte de 10 à 1 000 caractères (espaces de bord retirés). */
export function validateDispute(reason: string, text: string): "reason" | "description" | null {
  if (!isDisputeReason(reason)) return "reason";
  const length = text.trim().length;
  if (length < DISPUTE_MIN || length > DISPUTE_MAX) return "description";
  return null;
}

/** Vrai tant que l'échéance (UTC) n'est pas passée. Sans échéance valide : fermé. */
export function disputeWindowOpen(deadlineIso: string | null, now: string | Date): boolean {
  if (!deadlineIso) return false;
  const deadline = Date.parse(deadlineIso);
  const current = now instanceof Date ? now.getTime() : Date.parse(now);
  if (Number.isNaN(deadline) || Number.isNaN(current)) return false;
  return current < deadline;
}
