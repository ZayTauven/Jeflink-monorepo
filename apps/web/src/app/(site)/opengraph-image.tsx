// Image Open Graph par défaut du site public (accueil, pages sœurs, métiers) : slogan et logo.
import { getTranslations } from "next-intl/server";

import { OG_CONTENT_TYPE, OG_SIZE, renderOg } from "@/lib/site/og";

export const size = OG_SIZE;
export const contentType = OG_CONTENT_TYPE;
export const dynamic = "force-dynamic";

export default async function Image() {
  const t = await getTranslations("site.seo");
  return renderOg({ title: t("ogHome"), brand: t("siteName") });
}
