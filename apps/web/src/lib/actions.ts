import "server-only";

import { NextResponse, type NextRequest } from "next/server";

import { TOKEN_COOKIE, type ApiError } from "./api";

/**
 * Réponses des route handlers de formulaires (src/app/act/…).
 *
 * Le composant ActionForm envoie l'en-tête `x-jeflink-fetch` et reçoit du JSON (erreurs affichées
 * sans perdre la saisie). Sans JavaScript, le formulaire est posté normalement : on répond par
 * une redirection 303. Dans les deux cas la page suivante est un chargement complet, ce dont
 * les scripts Crafto ont besoin.
 */
export function wantsJson(req: NextRequest): boolean {
  return req.headers.get("x-jeflink-fetch") === "1";
}

/** Refuse un POST venu d'un autre site (le cookie SameSite=Lax protège déjà, ceci double). */
export function sameOrigin(req: NextRequest): boolean {
  const origin = req.headers.get("origin");
  return !origin || new URL(origin).host === req.headers.get("host");
}

export function forbidden() {
  return NextResponse.json({ ok: false, error: "Requête refusée." }, { status: 403 });
}

export function success(req: NextRequest, to: string, token?: string | null) {
  const res = wantsJson(req)
    ? NextResponse.json({ ok: true, redirect: to })
    : NextResponse.redirect(new URL(to, req.url), 303);
  if (token) {
    res.cookies.set(TOKEN_COOKIE, token, {
      httpOnly: true,
      sameSite: "lax",
      secure: process.env.NODE_ENV === "production",
      path: "/",
      maxAge: 60 * 60 * 24 * 30,
    });
  } else if (token === null) {
    res.cookies.delete(TOKEN_COOKIE);
  }
  return res;
}

export function failure(req: NextRequest, err: ApiError, back: string) {
  // Jeton expiré ou révoqué : on l'efface et on repasse par la connexion.
  if (err.status === 401) return success(req, `/connexion?suite=${encodeURIComponent(back)}`, null);
  if (wantsJson(req)) {
    return NextResponse.json({ ok: false, error: err.error, fields: err.fields });
  }
  const url = new URL(back, req.url);
  url.searchParams.set("erreur", err.error || "Une erreur est survenue.");
  return NextResponse.redirect(url, 303);
}

/** Chemin de retour interne uniquement (jamais vers un autre site). */
export function safeNext(value: FormDataEntryValue | null, fallback: string): string {
  const v = typeof value === "string" ? value : "";
  return v.startsWith("/") && !v.startsWith("//") && !v.startsWith("/\\") ? v : fallback;
}

export function text(form: FormData, key: string): string {
  const v = form.get(key);
  return typeof v === "string" ? v.trim() : "";
}
