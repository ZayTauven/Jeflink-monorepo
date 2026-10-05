// Chemins du site public : un seul helper (ADR 0013). Quand le wolof arrivera sous `/wo/…`, c'est
// ici que le préfixe de langue s'ajoutera, pas dans chaque lien. Les slugs ne sont jamais traduits.
// Modules purs, testés seuls.

export const SITE_PATHS = {
  home: "/",
  trades: "/metiers",
  howItWorks: "/#comment-ca-marche",
  about: "/a-propos",
  contact: "/contact",
  becomePro: "/devenir-pro",
  search: "/recherche",
  request: "/demande",
  account: "/compte/demandes",
  footer: "#pied-de-page",
  content: "#contenu",
} as const;

/** `/plombier` */
export function tradePath(tradeSlug: string): string {
  return `/${encodeURIComponent(tradeSlug)}`;
}

/** `/plombier/ouakam` */
export function tradeZonePath(tradeSlug: string, zoneSlug: string): string {
  return `${tradePath(tradeSlug)}/${encodeURIComponent(zoneSlug)}`;
}

export type DemandContext = {
  // `| undefined` : les props optionnelles de CtaContext passent telles quelles (exactOptionalPropertyTypes).
  metier?: string | null | undefined;
  quartier?: string | null | undefined;
  service?: string | null | undefined;
  urgence?: boolean | undefined;
};

/**
 * Lien pré-rempli vers `/demande` : `?metier=&quartier=&service=&urgence=1`, toujours dans cet
 * ordre. Le service n'a de sens qu'avec son métier. `/demande` revalide chaque slug contre le
 * catalogue et ignore ce qu'il ne connaît pas (spec 006, web 9) ; ici, aucune donnée de visiteur.
 */
export function demandPath({ metier, quartier, service, urgence }: DemandContext = {}): string {
  const params = new URLSearchParams();
  if (metier) params.set("metier", metier);
  if (quartier) params.set("quartier", quartier);
  if (metier && service) params.set("service", service);
  if (urgence) params.set("urgence", "1");
  const query = params.toString();
  return query ? `${SITE_PATHS.request}?${query}` : SITE_PATHS.request;
}
