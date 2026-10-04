// Frise d'une mission (spec 004, web 1) : de la réservation à la clôture. Module pur, testé seul.
// Le sens n'est jamais porté par la couleur : chaque étape a un mot et un état lisible.
import type { ClientBooking } from "@jeflink/api-client";

export const STEP_KEYS = [
  "scheduled",
  "en_route",
  "on_site",
  "in_progress",
  "completed",
  "closed",
] as const;
export type StepKey = (typeof STEP_KEYS)[number];
export type StepState = "done" | "current" | "upcoming";
export type Step = { key: StepKey; state: StepState; at: string | null };

type Timeline = Pick<
  ClientBooking,
  "status" | "en_route_at" | "on_site_at" | "started_at" | "completed_at" | "closed_at"
>;

/** Statuts où la mission est suivie : de la confirmation du pro à la clôture. */
const MISSION: readonly string[] = [
  "scheduled",
  "en_route",
  "on_site",
  "in_progress",
  "completed",
  "disputed",
  "closed",
];
/** Statuts où quelque chose peut encore changer sans geste du client : on actualise seul. */
const LIVE: readonly string[] = ["scheduled", "en_route", "on_site", "in_progress"];

export function isMission(status: string): boolean {
  return MISSION.includes(status);
}

/** La mission est en cours : l'actualisation automatique est permise (onglet visible). */
export function isMissionLive(status: string): boolean {
  return LIVE.includes(status);
}

/** Le code de fin est utile au client de la confirmation du pro jusqu'au travail en cours. */
export function isCodeStage(status: string): boolean {
  return LIVE.includes(status);
}

/** Étape en cours (0 à 5), ou null hors du déroulé (accepted, cancelled, inconnu). Litige : `completed`. */
export function currentStepIndex(status: string): number | null {
  switch (status) {
    case "scheduled":
      return 0;
    case "en_route":
      return 1;
    case "on_site":
      return 2;
    case "in_progress":
      return 3;
    case "completed":
    case "disputed":
      return 4;
    case "closed":
      return 5;
    default:
      return null;
  }
}

/** Les six étapes, avec leur état et l'heure où elles ont été atteintes. Null hors du déroulé. */
export function missionSteps(booking: Timeline): Step[] | null {
  const current = currentStepIndex(booking.status);
  if (current === null) return null;
  const times: (string | null)[] = [
    null,
    booking.en_route_at,
    booking.on_site_at,
    booking.started_at,
    booking.completed_at,
    booking.closed_at,
  ];
  const closed = booking.status === "closed";
  return STEP_KEYS.map((key, index) => {
    let state: StepState = "upcoming";
    if (closed || index < current) state = "done";
    else if (index === current) state = "current";
    return { key, state, at: state === "upcoming" ? null : (times[index] ?? null) };
  });
}
