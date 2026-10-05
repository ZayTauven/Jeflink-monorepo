// Image Open Graph d'une page métier : le titre du métier et le logo, sur un aplat. Un métier
// inconnu ou une panne de l'API donne l'image par défaut (jamais une erreur dans un aperçu).
import { getLocale, getTranslations } from "next-intl/server";

import { localized } from "@/lib/requests/catalog";
import { getTrade } from "@/lib/site/data";
import { OG_CONTENT_TYPE, OG_SIZE, renderOg } from "@/lib/site/og";

export const size = OG_SIZE;
export const contentType = OG_CONTENT_TYPE;
export const dynamic = "force-dynamic";

export default async function Image({ params }: { params: Promise<{ metier: string }> }) {
  const { metier } = await params;
  const t = await getTranslations("site.seo");
  const locale = await getLocale();
  let title = t("ogHome");
  try {
    const trade = await getTrade(metier);
    if (trade) title = localized(trade.seo_title, locale);
  } catch {
    // panne : image par défaut
  }
  return renderOg({ title, brand: t("siteName") });
}
