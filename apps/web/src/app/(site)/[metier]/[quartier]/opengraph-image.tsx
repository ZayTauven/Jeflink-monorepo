// Image Open Graph d'une page métier × quartier : « Plomberie à Ouakam » et le logo, sur un aplat.
// Titre composé comme celui de la page (locatif saisi, repli « à {nom} »). La paire est validée
// contre les listes en cache (métier, quartier, couverture) AVANT tout appel de détail : inconnue
// ou fermée, ou panne de l'API : image par défaut, sans appel.
import { getLocale, getTranslations } from "next-intl/server";

import { localized } from "@/lib/requests/catalog";
import { getTrade, getZone } from "@/lib/site/data";
import { knownOpenPair } from "@/lib/site/known";
import { tradeZoneTitle, zoneLocative } from "@/lib/site/locative";
import { OG_CONTENT_TYPE, OG_SIZE, renderOg } from "@/lib/site/og";

export const size = OG_SIZE;
export const contentType = OG_CONTENT_TYPE;
export const dynamic = "force-dynamic";

export default async function Image({
  params,
}: {
  params: Promise<{ metier: string; quartier: string }>;
}) {
  const { metier, quartier } = await params;
  const t = await getTranslations("site.seo");
  const locale = await getLocale();
  let title = t("ogHome");
  try {
    const pair = await knownOpenPair(metier, quartier);
    if (pair) {
      const [trade, zone] = await Promise.all([
        getTrade(pair.tradeSlug),
        getZone(pair.zoneSlug, pair.tradeSlug),
      ]);
      if (trade && zone) {
        title = tradeZoneTitle(
          localized(trade.seo_title, locale),
          zoneLocative(
            { name: zone.name, locative: zone.locative },
            (name) => t("locativeFallback", { name }),
            locale,
          ),
        );
      }
    }
  } catch {
    // panne : image par défaut
  }
  return renderOg({ title, brand: t("siteName") });
}
