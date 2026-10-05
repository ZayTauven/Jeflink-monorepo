// Métadonnées d'une page publique avec la copie i18n (marque, locale). Les règles de longueur et
// de canonical sont dans `seo.ts` (pur). Le canonical est relatif : `metadataBase` (SITE_URL) le
// rend absolu.
import "server-only";

import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";

import { pageMetadata } from "./seo.ts";

export async function buildMetadata(input: {
  title: string;
  description: string;
  ogDescription?: string;
  path: string;
  indexable?: boolean;
}): Promise<Metadata> {
  const t = await getTranslations("site.seo");
  return pageMetadata({
    ...input,
    fullTitle: t("titleTemplate", { title: input.title }),
    siteName: t("siteName"),
    locale: t("locale"),
  });
}
