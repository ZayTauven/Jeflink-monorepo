// Langue de la requête (règle 6 : fr par défaut, wo prévu). En attendant le routage par langue
// des pages SEO, la langue vient du cookie NEXT_LOCALE ; toute autre valeur donne le français.
// Les textes wolof sont écrits et validés par l'équipe (Q12) : une clé absente de wo.json
// retombe sur le français.
import { cookies, headers } from "next/headers";
import { getRequestConfig } from "next-intl/server";

import fr from "../../messages/fr.json";
import { PATH_HEADER } from "../lib/routes.ts";
import { usesLocaleCookie } from "./locale-scope.ts";

export const LOCALES = ["fr", "wo"] as const;
export type Locale = (typeof LOCALES)[number];
export const DEFAULT_LOCALE: Locale = "fr";

type Messages = { [key: string]: string | Messages };

function isLocale(value: string | undefined): value is Locale {
  return LOCALES.some((locale) => locale === value);
}

/** Textes de `override` par-dessus `base`, clé par clé (un espace de noms partiel ne vide rien). */
function withFallback(base: Messages, override: Messages): Messages {
  const merged: Messages = { ...base };
  for (const [key, value] of Object.entries(override)) {
    const fallback = merged[key];
    merged[key] =
      typeof value === "object" && typeof fallback === "object"
        ? withFallback(fallback, value)
        : value;
  }
  return merged;
}

export default getRequestConfig(async () => {
  // Le site public est en français pour tout le monde (ADR 0013) : le cookie ne compte que pour
  // l'espace client. Une page publique ne lit donc jamais un cookie du visiteur.
  const path = (await headers()).get(PATH_HEADER);
  const requested = usesLocaleCookie(path) ? (await cookies()).get("NEXT_LOCALE")?.value : undefined;
  const locale = isLocale(requested) ? requested : DEFAULT_LOCALE;
  if (locale === "fr") return { locale, messages: fr };
  const wo: Messages = (await import("../../messages/wo.json")).default;
  return { locale, messages: withFallback(fr, wo) };
});
