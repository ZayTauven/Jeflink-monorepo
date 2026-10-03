// Configuration publique du site lue à l'exécution (variables serveur, jamais NEXT_PUBLIC_) :
// une valeur changée ne demande pas de rebuild. Module pur, comme bff-config.ts.
import { BffConfigError } from "./bff-config.ts";

type Env = Record<string, string | undefined>;

export type SiteConfig = {
  /** Numéro WhatsApp du support, en chiffres E.164 sans « + » ; null en dev s'il manque. */
  supportWhatsapp: string | null;
};

export function readSiteConfig(env: Env): SiteConfig {
  const production = env.NODE_ENV !== "development";
  const raw = env.SUPPORT_WHATSAPP_NUMBER?.trim() ?? "";
  const digits = raw.replace(/[\s.-]/g, "").replace(/^\+/, "");
  if (raw && !/^[1-9][0-9]{7,14}$/.test(digits)) {
    throw new BffConfigError("SUPPORT_WHATSAPP_NUMBER", "n'est pas un numéro E.164");
  }
  // « Aucune impasse » (T3) : chaque erreur d'auth propose le support.
  if (production && !raw) {
    throw new BffConfigError("SUPPORT_WHATSAPP_NUMBER", "est obligatoire en production");
  }
  return { supportWhatsapp: raw ? digits : null };
}
