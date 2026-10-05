// Messages transmis au navigateur. `NextIntlClientProvider` (next-intl v4) hérite sinon de tout
// `fr.json` : des centaines de lignes de l'espace client (`requests.*`, `bookings.*`…) iraient à
// chaque page publique. Les pages publiques n'envoient que les messages de leurs îlots client
// (menu mobile, pause du bandeau, page d'erreur). Module pur, testé seul.

export type Messages = { [key: string]: string | Messages };

/** Espaces de noms utilisés par les composants client du site public. */
export const SITE_CLIENT_NAMESPACES = ["site.menu", "site.marquee", "site.search", "site.error", "site.newTab"] as const;

/** Sous-arbre de `messages` à `path` (« site.menu »), ou undefined s'il n'existe pas. */
function subtree(messages: Messages, path: readonly string[]): string | Messages | undefined {
  let node: string | Messages | undefined = messages;
  for (const key of path) {
    if (typeof node !== "object") return undefined;
    node = node[key];
  }
  return node;
}

/** Copie de `messages` limitée aux espaces de noms demandés (chemins pointés). */
export function pickMessages(messages: Messages, namespaces: readonly string[]): Messages {
  const picked: Messages = {};
  for (const namespace of namespaces) {
    const path = namespace.split(".");
    const value = subtree(messages, path);
    if (value === undefined) continue;
    let cursor = picked;
    for (const key of path.slice(0, -1)) {
      const existing = cursor[key];
      if (typeof existing === "object") {
        cursor = existing;
      } else {
        const next: Messages = {};
        cursor[key] = next;
        cursor = next;
      }
    }
    cursor[path[path.length - 1] as string] = value;
  }
  return picked;
}
