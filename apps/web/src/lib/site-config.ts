// Configuration publique du site lue à l'exécution (variables serveur, jamais NEXT_PUBLIC_) :
// une valeur changée ne demande pas de rebuild. Module pur, comme bff-config.ts.
// Spec 006 (web 1) : SITE_URL, SITE_INDEXABLE, SITE_LEGAL_NAME, SUPPORT_PHONE_NUMBER.
import { BffConfigError } from "./bff-config.ts";

type Env = Record<string, string | undefined>;

export type SiteConfig = {
  /** Numéro WhatsApp du support, en chiffres E.164 sans « + » ; null en dev s'il manque. */
  supportWhatsapp: string | null;
  /** Numéro d'appel du support, E.164 avec « + » (lien `tel:`) ; null s'il n'est pas configuré. */
  supportPhone: string | null;
  /** Origine publique du site (`https://hôte`, sans chemin) ; null si elle n'est pas configurée. */
  siteUrl: string | null;
  /** Vrai seulement si l'Ops l'a décidé : sinon `robots.txt` interdit tout et `noindex` global. */
  indexable: boolean;
  /** Raison sociale (ou nom provisoire) affichée en pied de page, contre l'usurpation. */
  legalName: string | null;
};

/** Origine utilisée pour `metadataBase` quand `SITE_URL` manque (dev, staging non indexable). */
export const FALLBACK_SITE_ORIGIN = "http://localhost:3000";

function value(env: Env, name: string): string | undefined {
  const raw = env[name]?.trim();
  return raw ? raw : undefined;
}

/** Chiffres E.164 sans « + », ou null si la variable est vide ; refuse tout autre format. */
function phoneDigits(env: Env, name: string): string | null {
  const raw = value(env, name) ?? "";
  const digits = raw.replace(/[\s.-]/g, "").replace(/^\+/, "");
  if (raw && !/^[1-9][0-9]{7,14}$/.test(digits)) {
    throw new BffConfigError(name, "n'est pas un numéro E.164");
  }
  return raw ? digits : null;
}

function readSiteUrl(env: Env): string | null {
  const raw = value(env, "SITE_URL");
  if (!raw) return null;
  let url: URL;
  try {
    url = new URL(raw);
  } catch {
    throw new BffConfigError("SITE_URL", "n'est pas une URL");
  }
  if (url.protocol !== "https:" && url.protocol !== "http:") {
    throw new BffConfigError("SITE_URL", "doit commencer par https://");
  }
  if (url.username || url.password || (url.pathname !== "/" && url.pathname !== "")) {
    throw new BffConfigError("SITE_URL", "doit être une origine, sans chemin ni identifiants");
  }
  return url.origin;
}

function readIndexable(env: Env): boolean {
  const raw = value(env, "SITE_INDEXABLE")?.toLowerCase();
  if (raw === undefined || raw === "false") return false;
  if (raw === "true") return true;
  // Une faute de frappe ne doit pas ouvrir (ni fermer) l'indexation en silence.
  throw new BffConfigError("SITE_INDEXABLE", "doit valoir true ou false");
}

export function readSiteConfig(env: Env): SiteConfig {
  const production = env.NODE_ENV !== "development";
  const supportWhatsapp = phoneDigits(env, "SUPPORT_WHATSAPP_NUMBER");
  // « Aucune impasse » (T3) : chaque erreur d'auth propose le support.
  if (production && !supportWhatsapp) {
    throw new BffConfigError("SUPPORT_WHATSAPP_NUMBER", "est obligatoire en production");
  }
  const phone = phoneDigits(env, "SUPPORT_PHONE_NUMBER");
  const siteUrl = readSiteUrl(env);
  const legalName = value(env, "SITE_LEGAL_NAME") ?? null;
  const indexable = readIndexable(env);

  if (indexable) {
    // Ce qui ne se vérifie pas en code (procédure « Pro vérifié », licences d'images, intros)
    // est une condition de passage de docs/architecture/chantier-prod.md.
    if (!siteUrl) throw new BffConfigError("SITE_URL", "est obligatoire quand SITE_INDEXABLE=true");
    if (new URL(siteUrl).protocol !== "https:") {
      throw new BffConfigError("SITE_URL", "doit être en https quand SITE_INDEXABLE=true");
    }
    if (!supportWhatsapp) {
      throw new BffConfigError(
        "SUPPORT_WHATSAPP_NUMBER",
        "est obligatoire quand SITE_INDEXABLE=true",
      );
    }
    if (!phone) {
      throw new BffConfigError("SUPPORT_PHONE_NUMBER", "est obligatoire quand SITE_INDEXABLE=true");
    }
    if (!legalName) {
      throw new BffConfigError("SITE_LEGAL_NAME", "est obligatoire quand SITE_INDEXABLE=true");
    }
  }

  return {
    supportWhatsapp,
    supportPhone: phone ? `+${phone}` : null,
    siteUrl,
    indexable,
    legalName,
  };
}
