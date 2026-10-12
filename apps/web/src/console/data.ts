import "server-only";

import { notFound, redirect } from "next/navigation";

import { api, requireStaff } from "@/lib/api";

export type Query = Record<string, string | undefined>;

/** Chaîne de requête sans les paramètres vides (et sans les messages de retour). */
export function qs(params: Query, changes: Query = {}): string {
  const out = new URLSearchParams();
  for (const [k, v] of Object.entries({ ...params, ...changes })) {
    if (v && k !== "ok" && k !== "erreur") out.set(k, v);
  }
  const s = out.toString();
  return s ? `?${s}` : "";
}

/**
 * Lecture pour une page de la console : vérifie l'accès (chaque page, pas seulement le layout),
 * puis appelle l'API. 404 de l'API → page introuvable ; autre erreur → exception (error.tsx).
 */
export async function consoleGet<T>(here: string, path: string, params: Query = {}): Promise<T> {
  const { token } = await requireStaff(here);
  const res = await api<T>(`/api/console/${path}${qs(params)}`, { token });
  if (res.ok) return res.data;
  if (res.status === 404) notFound();
  if (res.status === 403) {
    redirect(
      `/console?erreur=${encodeURIComponent("Cette rubrique n'est pas ouverte à votre rôle.")}`,
    );
  }
  throw new Error(res.error || "La console ne répond pas.");
}
