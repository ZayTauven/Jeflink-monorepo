// Photos d'une mission (spec 004, web 2). Les URL sont signées pour 10 minutes : une URL expirée
// se renouvelle en rechargeant la réservation. Seules les miniatures se chargent par défaut.
import type { Photo } from "@jeflink/api-client";

export type PhotoPhase = "before" | "after";
export const PHOTO_PHASES: readonly PhotoPhase[] = ["before", "after"];

/** L'URL signée a expiré (ou son échéance est illisible : dans le doute, on recharge). */
export function isExpired(expiresAt: string, now: string | Date = new Date()): boolean {
  const end = Date.parse(expiresAt);
  const current = now instanceof Date ? now.getTime() : Date.parse(now);
  if (Number.isNaN(end) || Number.isNaN(current)) return true;
  return current >= end;
}

/** Photos affichables d'une phase, dans l'ordre de prise. Les photos en échec n'apparaissent pas. */
export function photosOf<T extends Pick<Photo, "phase" | "status" | "created_at">>(
  photos: readonly T[],
  phase: PhotoPhase,
): T[] {
  return photos
    .filter((photo) => photo.phase === phase && photo.status !== "failed")
    .sort((a, b) => Date.parse(a.created_at) - Date.parse(b.created_at));
}
