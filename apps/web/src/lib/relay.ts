import "server-only";

import { API_URL, getToken } from "./api";

/** En-têtes de l'API gardés tels quels : type, téléchargement, cache et sécurité. */
const KEEP = [
  "content-type",
  "content-disposition",
  "content-length",
  "cache-control",
  "content-security-policy",
  "x-content-type-options",
  "cross-origin-resource-policy",
  "referrer-policy",
];

/**
 * Relaie un fichier privé de l'API (document d'un pro, photo d'une demande) avec le jeton du
 * cookie. L'API décide qui y a droit ; ici on ne fait que transmettre, sans cache.
 */
export async function relayFile(apiPath: string): Promise<Response> {
  const token = await getToken();
  if (!token) return new Response("Introuvable.", { status: 404 });
  let res: Response;
  try {
    res = await fetch(`${API_URL}${apiPath}`, {
      headers: { Authorization: `Token ${token}` },
      cache: "no-store",
    });
  } catch {
    return new Response("L'API Jeflink ne répond pas.", { status: 503 });
  }
  if (!res.ok || !res.body) return new Response("Introuvable.", { status: 404 });
  const headers = new Headers();
  for (const name of KEEP) {
    const value = res.headers.get(name);
    if (value) headers.set(name, value);
  }
  return new Response(res.body, { status: 200, headers });
}
