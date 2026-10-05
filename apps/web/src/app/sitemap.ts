// sitemap.xml (spec 006, web 10) : pages fixes, métiers et paires indexables, via `catalog/coverage`.
// Rendu à la requête (les données sont dans le cache de `publicApi()`, 5 min) : une fermeture ou une
// réouverture saisie par l'Ops se voit en 5 minutes au plus. Sans SITE_URL : vide (staging, local).
import type { MetadataRoute } from "next";

import { getCoverage, getTrades } from "@/lib/site/data";
import { buildSitemap } from "@/lib/site/sitemap";
import { readSiteConfig } from "@/lib/site-config";

export const dynamic = "force-dynamic";

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const { siteUrl } = readSiteConfig(process.env);
  if (!siteUrl) return [];
  const [trades, coverage] = await Promise.all([getTrades(), getCoverage()]);
  return buildSitemap({ origin: siteUrl, tradeSlugs: trades.map((trade) => trade.slug), coverage });
}
