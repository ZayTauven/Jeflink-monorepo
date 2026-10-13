import "server-only";

import { NextResponse } from "next/server";

import type { ApiResult } from "./api";
import type { JefSession } from "./types";

/** Réponse JSON des routes /act/jef pour le composant Jef (il n'existe qu'avec JavaScript). */
export function jefReply(res: ApiResult<JefSession>) {
  if (res.ok) return NextResponse.json({ ok: true, session: res.data });
  const error =
    res.status === 401
      ? "Votre session a expiré. Reconnectez-vous pour utiliser Jef."
      : Object.values(res.fields)[0] || res.error || "Jef ne répond pas. Réessayez.";
  return NextResponse.json({ ok: false, error }, { status: res.status >= 500 ? 502 : 200 });
}
