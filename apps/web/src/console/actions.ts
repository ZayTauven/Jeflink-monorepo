"use server";

/**
 * Action serveur des formulaires de la console : POST vers une action de l'API console, puis
 * retour sur la page avec un message (?ok= ou ?erreur=). Fonctionne sans JavaScript.
 * `submitConsoleAction` (avec JavaScript, `ActionForm`) : même chose, mais une erreur est
 * renvoyée au formulaire au lieu de recharger la page (la saisie reste, la fenêtre aussi).
 *
 * Champs réservés : _endpoint (action API, liste blanche), _back (page de retour, /console…),
 * _ok (message de réussite). Les autres champs texte forment le corps JSON.
 */
import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";

import { api, requireStaff } from "@/lib/api";

// Actions autorisées : action sur un élément, création (métier, quartier, membre, code promo,
// campagne), réglages, commissions.
const ENDPOINT = new RegExp(
  "^/api/console/(?:" +
    "(?:requests|disputes|pros|clients|reviews|messages|trades|zones|team|coupons|campaigns|balances)/\\d+/(?:[a-z]+|confirm-cancel)/" +
    "|(?:trades|zones|team|coupons|campaigns)/" +
    "|settings/|commissions/" +
    ")$",
);
const BASE = "http://console.invalid";

function backTo(value: FormDataEntryValue | null): URL {
  const url = new URL(
    typeof value === "string" && value.startsWith("/") ? value : "/console",
    BASE,
  );
  if (url.origin !== BASE || !url.pathname.startsWith("/console")) return new URL("/console", BASE);
  url.searchParams.delete("ok");
  url.searchParams.delete("erreur");
  return url;
}

function done(url: URL, key: "ok" | "erreur", message: string): never {
  url.searchParams.set(key, message);
  redirect(url.pathname + url.search + url.hash);
}

/** Envoie l'action ; réussite : retour sur la page avec le message, sinon l'erreur à afficher. */
async function perform(form: FormData): Promise<{ back: URL; error: string }> {
  const back = backTo(form.get("_back"));
  const endpoint = String(form.get("_endpoint") ?? "");
  if (!ENDPOINT.test(endpoint)) return { back, error: "Action inconnue." };

  const { token } = await requireStaff(back.pathname);
  // Champ « nom[] » → tableau (cases à cocher multiples) ; sinon la dernière valeur l'emporte
  // (une case simple envoie « 0 » caché puis « 1 » si cochée).
  const body: Record<string, string | string[]> = {};
  for (const [key, value] of form.entries()) {
    if (key.startsWith("_") || key.startsWith("$") || typeof value !== "string") continue;
    if (key.endsWith("[]")) {
      const name = key.slice(0, -2);
      const list = body[name];
      body[name] = Array.isArray(list) ? [...list, value] : [value];
    } else {
      body[key] = value;
    }
  }
  const res = await api(endpoint, { method: "POST", token, body });
  if (res.ok) {
    // Sans cela, revenir sur une adresse déjà visitée (même message) peut réafficher
    // l'ancienne version de la page gardée par le routeur.
    revalidatePath(back.pathname);
    done(back, "ok", String(form.get("_ok") || "C'est fait."));
  }
  return {
    back,
    error: res.error || Object.values(res.fields)[0] || "L'action n'a pas abouti. Réessayez.",
  };
}

export async function consoleAction(form: FormData) {
  const { back, error } = await perform(form);
  done(back, "erreur", error);
}

export async function submitConsoleAction(form: FormData): Promise<{ error: string }> {
  const { error } = await perform(form);
  return { error };
}
