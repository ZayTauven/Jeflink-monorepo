// Plan du site et robots.txt (spec 006, web 10). Modules purs, testés seuls.
// - Sitemap : pages fixes, métiers, et paires métier × quartier `indexable` seulement ; les alias
//   n'y entrent jamais, ni `/recherche`. `lastModified` = `updated_at` de la couverture.
// - robots.txt : tout interdit tant que SITE_INDEXABLE n'est pas vrai ; sinon les pages privées
//   (`/compte`, `/demande`, `/connexion`, `/recherche`, `/api/`) sont exclues et le sitemap annoncé.
import { SITE_PATHS, tradePath, tradeZonePath } from "./paths.ts";
import { absoluteUrl } from "./seo.ts";

export type SitemapEntry = { url: string; lastModified?: Date };

export type CoverageInput = { trade: string; zone: string; indexable: boolean; updated_at: string };

const FIXED_PATHS = [
  SITE_PATHS.home,
  SITE_PATHS.trades,
  SITE_PATHS.about,
  SITE_PATHS.contact,
  SITE_PATHS.becomePro,
];

function parseDate(value: string): Date | undefined {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? undefined : date;
}

export function buildSitemap(input: {
  origin: string;
  tradeSlugs: readonly string[];
  coverage: readonly CoverageInput[];
}): SitemapEntry[] {
  const entries: SitemapEntry[] = FIXED_PATHS.map((path) => ({ url: absoluteUrl(input.origin, path) }));
  for (const slug of input.tradeSlugs) {
    const dates = input.coverage
      .filter((pair) => pair.trade === slug)
      .map((pair) => parseDate(pair.updated_at))
      .filter((date): date is Date => date !== undefined);
    const latest = dates.length ? new Date(Math.max(...dates.map((date) => date.getTime()))) : undefined;
    entries.push({
      url: absoluteUrl(input.origin, tradePath(slug)),
      ...(latest ? { lastModified: latest } : {}),
    });
  }
  for (const pair of input.coverage) {
    if (!pair.indexable) continue;
    const lastModified = parseDate(pair.updated_at);
    entries.push({
      url: absoluteUrl(input.origin, tradeZonePath(pair.trade, pair.zone)),
      ...(lastModified ? { lastModified } : {}),
    });
  }
  return entries;
}

export type RobotsConfig = {
  rules: { userAgent: string; allow?: string; disallow: string | string[] };
  sitemap?: string;
};

export const PRIVATE_PATHS = ["/compte", "/demande", "/connexion", "/recherche", "/api/"] as const;

export function buildRobots(input: { indexable: boolean; origin: string | null }): RobotsConfig {
  if (!input.indexable) return { rules: { userAgent: "*", disallow: "/" } };
  return {
    rules: { userAgent: "*", allow: "/", disallow: [...PRIVATE_PATHS] },
    ...(input.origin ? { sitemap: absoluteUrl(input.origin, "/sitemap.xml") } : {}),
  };
}
