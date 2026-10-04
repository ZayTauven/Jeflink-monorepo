// Proxy Next des PAGES (jamais /api : le BFF a ses propres règles, sa page de rebond sa propre CSP).
//
// - Une seule forme d'URL par page, sans barre finale (`skipTrailingSlashRedirect` est voulu pour
//   /api, où Django exige la barre).
// - CSP à nonce, neuve à chaque requête ; Next l'applique à ses scripts.
// - Chemin courant transmis aux Server Components par `x-jf-path`, toujours posé ici avec `set` :
//   une valeur venue du navigateur est écrasée. Il est revalidé par `refreshRedirectPath`.
// - Page demandée avec une session : `Cache-Control: private, no-store`, posé ici et gardé par
//   Next ; aucun cache partagé ne sert la page d'un client à un autre (revue web 1, I-2). Next
//   réécrit `Vary` : c'est ce `no-store`, et la règle du bord (infra/README.md), qui protègent.
import { type NextRequest, NextResponse } from "next/server";

import { PATH_HEADER } from "./lib/routes.ts";
import { storageOrigin } from "./lib/storage-origin.ts";

// Cookies qui signalent une session (accès, ou témoin d'un refresh possible).
const SESSION_COOKIES = ["__Host-jf_at", "__Host-jf_sess"];

function contentSecurityPolicy(nonce: string): string {
  const dev = process.env.NODE_ENV === "development";
  const storage = storageOrigin(process.env);
  return [
    "default-src 'self'",
    // `unsafe-eval` en dev seulement : React s'en sert pour ses traces d'erreur.
    `script-src 'self' 'nonce-${nonce}' 'strict-dynamic'${dev ? " 'unsafe-eval'" : ""}`,
    // Dev : Next injecte ses styles en ligne (indicateur, rechargement) ; un nonce rendrait
    // `unsafe-inline` inopérant, d'où une directive à part. Production : nonce strict.
    dev ? "style-src 'self' 'unsafe-inline'" : `style-src 'self' 'nonce-${nonce}'`,
    // Photos de mission : miniatures et images signées servies par le stockage d'objets.
    `img-src 'self' blob: data:${storage ? ` ${storage}` : ""}`,
    "font-src 'self'",
    "connect-src 'self'",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
    ...(dev ? [] : ["upgrade-insecure-requests"]),
  ].join("; ");
}

export function proxy(request: NextRequest): NextResponse {
  // URL standard : NextURL garde la barre finale d'origine à la sérialisation (boucle de 308).
  const url = new URL(request.url);
  if (url.pathname.length > 1 && url.pathname.endsWith("/")) {
    url.pathname = url.pathname.replace(/\/+$/, "") || "/";
    return NextResponse.redirect(url, 308);
  }

  const nonce = btoa(String.fromCharCode(...crypto.getRandomValues(new Uint8Array(16))));
  const csp = contentSecurityPolicy(nonce);
  const headers = new Headers(request.headers);
  headers.set("content-security-policy", csp);
  headers.set(PATH_HEADER, `${url.pathname}${url.search}`);

  const response = NextResponse.next({ request: { headers } });
  response.headers.set("Content-Security-Policy", csp);
  if (SESSION_COOKIES.some((name) => request.cookies.has(name))) {
    response.headers.set("Cache-Control", "private, no-store");
  }
  return response;
}

export const config = {
  // Ni /api (BFF), ni les fichiers de Next, ni les fichiers publics. Fichiers exclus par leur nom
  // exact (ancré) : `/robots.txt-x/…` reste une page, avec CSP et x-jf-path (revue web 1, m-4).
  matcher: ["/((?!api/|api$|_next/|favicon\\.ico$|robots\\.txt$|sitemap\\.xml$).*)"],
};
