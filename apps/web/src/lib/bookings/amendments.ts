// Avenants (spec 004, web 2) : un nouveau prix complet que le client accepte ou refuse. Aucun prix
// ne change sans son geste. Au-delà du seuil de hausse (réglage de l'API, `requires_confirmation`),
// une étape de confirmation s'ajoute dans la page ; une baisse n'en demande jamais.
import type { Amendment } from "@jeflink/api-client";

type Priced = Pick<Amendment, "previous_amount_xof" | "total_xof">;

export type Direction = "up" | "down" | "same";

export function direction(amendment: Priced): Direction {
  if (amendment.total_xof > amendment.previous_amount_xof) return "up";
  if (amendment.total_xof < amendment.previous_amount_xof) return "down";
  return "same";
}

/** L'avenant en attente de décision (au plus un à la fois côté API). */
export function pendingAmendment<T extends Pick<Amendment, "status">>(
  amendments: readonly T[],
): T | undefined {
  return amendments.find((amendment) => amendment.status === "proposed");
}

/** Confirmation en plus du geste : hausse au-delà du seuil seulement. */
export function needsConfirmation(
  amendment: Priced &
    Pick<Amendment, "status" | "requires_confirmation"> &
    Partial<Pick<Amendment, "change_pct">>,
): boolean {
  return (
    amendment.status === "proposed" &&
    amendment.requires_confirmation &&
    direction(amendment) === "up"
  );
}

/** Écart en % pour l'affichage, entier et sans signe (le sens est dit par un mot : hausse, baisse). */
export function changePercent(amendment: Priced & Pick<Amendment, "change_pct">): number {
  const given = Math.abs(amendment.change_pct);
  if (Number.isFinite(given)) return Math.round(given);
  if (amendment.previous_amount_xof <= 0) return 0;
  return Math.round(
    (Math.abs(amendment.total_xof - amendment.previous_amount_xof) * 100) /
      amendment.previous_amount_xof,
  );
}
