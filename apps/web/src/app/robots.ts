// robots.txt (spec 006, web 10) : tout est interdit tant que SITE_INDEXABLE n'est pas vrai (défaut,
// en local et en staging) ; sinon les pages privées sont exclues et le sitemap annoncé.
import type { MetadataRoute } from "next";

import { buildRobots } from "@/lib/site/sitemap";
import { readSiteConfig } from "@/lib/site-config";

export const dynamic = "force-dynamic";

export default function robots(): MetadataRoute.Robots {
  const { indexable, siteUrl } = readSiteConfig(process.env);
  return buildRobots({ indexable, origin: siteUrl });
}
