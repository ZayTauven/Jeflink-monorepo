// Origine du stockage des photos (spec 004, web 2) : les URL signées de l'API pointent vers le
// stockage d'objets, un autre hôte que le site. La CSP doit l'autoriser dans `img-src`, et
// seulement lui. Variable SERVEUR lue à la requête (jamais NEXT_PUBLIC_, jamais figée au build),
// sans secret : une origine, rien d'autre.

type Env = Record<string, string | undefined>;

const DEV_ORIGIN = "http://localhost:8333";

/** Origine `https://hôte[:port]` du stockage, ou null. Valeur illisible ou autre schéma : null. */
export function storageOrigin(env: Env): string | null {
  const raw = env.STORAGE_PUBLIC_ORIGIN?.trim();
  if (!raw) return env.NODE_ENV === "development" ? DEV_ORIGIN : null;
  try {
    const url = new URL(raw);
    if (url.protocol !== "https:" && url.protocol !== "http:") return null;
    // En production, jamais de http : l'URL signée contient une signature.
    if (env.NODE_ENV !== "development" && url.protocol !== "https:") return null;
    return url.origin;
  } catch {
    return null;
  }
}
