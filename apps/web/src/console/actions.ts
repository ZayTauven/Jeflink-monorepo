"use server";

/**
 * Action serveur unique des formulaires de la console : POST vers une action de l'API console,
 * puis retour sur la page avec un message (?ok= ou ?erreur=). Fonctionne sans JavaScript.
 *
 * Champs réservés : _endpoint (action API, liste blanche), _back (page de retour, /console…),
 * _ok (message de réussite). Les autres champs texte forment le corps JSON.
 */
import { redirect } from "next/navigation";

import { api, requireStaff } from "@/lib/api";

const ENDPOINT =
  /^\/api\/console\/(requests|disputes|pros|clients|reviews|messages)\/\d+\/[a-z]+\/$/;
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

export async function consoleAction(form: FormData) {
  const back = backTo(form.get("_back"));
  const endpoint = String(form.get("_endpoint") ?? "");
  if (!ENDPOINT.test(endpoint)) done(back, "erreur", "Action inconnue.");

  const { token } = await requireStaff(back.pathname);
  const body: Record<string, string> = {};
  for (const [key, value] of form.entries()) {
    if (!key.startsWith("_") && !key.startsWith("$") && typeof value === "string") {
      body[key] = value;
    }
  }
  const res = await api(endpoint, { method: "POST", token, body });
  if (res.ok) done(back, "ok", String(form.get("_ok") || "C'est fait."));
  done(
    back,
    "erreur",
    res.error || Object.values(res.fields)[0] || "L'action n'a pas abouti. Réessayez.",
  );
}
