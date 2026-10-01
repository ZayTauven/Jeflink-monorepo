// Configuration du BFF de l'app web, lue depuis les variables SERVEUR à l'exécution (jamais au
// build, jamais en NEXT_PUBLIC_). Module pur : l'environnement est passé en paramètre, pour les
// tests ; seul `lib/bff.ts` (server-only) l'appelle avec process.env.
import type { BffConfig } from "@jeflink/api-client/bff";

/** Durée du cookie de refresh web : 30 j d'inactivité (Q4). Django borne la session à 90 j. */
export const WEB_REFRESH_MAX_AGE_SECONDS = 30 * 24 * 3600;
export const LOGIN_PATH = "/connexion";
/** Chemin courant d'une page, posé par src/proxy.ts (jamais repris du navigateur). */
export const PATH_HEADER = "x-jf-path";
const DEV_ORIGIN = "http://localhost:3000";
const DEV_API_URL = "http://localhost:8000";
const DEV_CLIENT_IP = "127.0.0.1";
// En-têtes qu'un client peut fabriquer ou allonger : jamais une source d'IP (spec 001, S9).
const REFUSED_IP_HEADERS = new Set(["x-forwarded-for", "forwarded"]);

type Env = Record<string, string | undefined>;

export class BffConfigError extends Error {
  constructor(variable: string, reason: string) {
    // Le nom de la variable seulement, jamais sa valeur.
    super(`BFF web : ${variable} ${reason}.`);
    this.name = "BffConfigError";
  }
}

function value(env: Env, name: string): string | undefined {
  const raw = env[name]?.trim();
  return raw ? raw : undefined;
}

export function readBffConfig(env: Env): BffConfig {
  const production = env.NODE_ENV === "production";

  const secret = value(env, "BFF_SHARED_SECRET");
  if (!secret) throw new BffConfigError("BFF_SHARED_SECRET", "est absente");

  const apiUrl = value(env, "JEFLINK_API_URL") ?? (production ? undefined : DEV_API_URL);
  if (!apiUrl) throw new BffConfigError("JEFLINK_API_URL", "est absente");
  if (production && !apiUrl.startsWith("https://")) {
    throw new BffConfigError("JEFLINK_API_URL", "doit être en https en production");
  }

  const origins = (value(env, "BFF_ALLOWED_ORIGINS") ?? (production ? "" : DEV_ORIGIN))
    .split(",")
    .map((origin) => origin.trim())
    .filter(Boolean);
  if (!origins.length) throw new BffConfigError("BFF_ALLOWED_ORIGINS", "est absente");
  if (production && origins.some((origin) => !origin.startsWith("https://"))) {
    throw new BffConfigError("BFF_ALLOWED_ORIGINS", "doit lister des origines https");
  }

  const ipHeader = value(env, "BFF_CLIENT_IP_HEADER")?.toLowerCase();
  if (
    ipHeader !== undefined &&
    (REFUSED_IP_HEADERS.has(ipHeader) || !/^[a-z0-9-]+$/.test(ipHeader))
  ) {
    throw new BffConfigError("BFF_CLIENT_IP_HEADER", "n'est pas une source d'IP acceptée");
  }
  if (production && !ipHeader) {
    throw new BffConfigError("BFF_CLIENT_IP_HEADER", "est obligatoire en production");
  }

  const cookieDomain = value(env, "BFF_COOKIE_DOMAIN")?.toLowerCase();
  if (cookieDomain !== undefined && !/^[a-z0-9-]+(\.[a-z0-9-]+)+$/.test(cookieDomain)) {
    throw new BffConfigError("BFF_COOKIE_DOMAIN", "n'est pas un nom de domaine");
  }
  // Production : un refresh planté par un sous-domaine doit pouvoir être effacé (revue BFF, m1).
  if (production && !cookieDomain) {
    throw new BffConfigError("BFF_COOKIE_DOMAIN", "est obligatoire en production");
  }

  return {
    app: "web",
    apiUrl,
    allowedOrigins: origins,
    bffSecret: secret,
    // Le BFF ignore toute valeur qui n'est pas une adresse IP (liste, port, texte).
    clientIp: ipHeader ? (headers) => headers.get(ipHeader)?.trim() ?? null : () => DEV_CLIENT_IP,
    refreshMaxAgeSeconds: WEB_REFRESH_MAX_AGE_SECONDS,
    loginPath: LOGIN_PATH,
    ...(cookieDomain ? { cookieDomain } : {}),
  };
}
