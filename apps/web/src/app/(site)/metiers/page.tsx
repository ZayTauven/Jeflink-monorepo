// /metiers. Question métier : « Quels métiers Jeflink propose-t-il ? ». Action principale : choisir
// un métier (une carte = un lien). Page sœur « services » de Crafto : titre en deux blocs, une
// carte par métier (image par `icon_key`, pictogramme et libellé, description courte), puis
// « Comment ça marche ». Sans catalogue (API en panne) : le CTA WhatsApp remplace la liste.
import type { Metadata } from "next";
import { getLocale, getTranslations } from "next-intl/server";

import { ActionBar } from "@/components/site/action-bar";
import { CtaPair } from "@/components/site/cta-pair";
import { HowSection, PageHeader, Section } from "@/components/site/sections";
import { TradeCard } from "@/components/site/trade-card";
import { localized } from "@/lib/requests/catalog";
import { getStats, getTrades, softly } from "@/lib/site/data";
import { buildMetadata } from "@/lib/site/metadata";
import { SITE_PATHS } from "@/lib/site/paths";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("site.trades");
  return buildMetadata({
    title: t("metaTitle"),
    description: t("metaDescription"),
    path: SITE_PATHS.trades,
  });
}

export default async function TradesPage() {
  const t = await getTranslations("site.trades");
  const locale = await getLocale();
  const [list, stats] = await Promise.all([softly(getTrades), getStats()]);
  const trades = list.map((trade) => ({
    slug: trade.slug,
    name: localized(trade.name, locale),
    iconKey: trade.icon_key,
    description: trade.short_description ? localized(trade.short_description, locale) : null,
  }));
  return (
    <>
      <PageHeader title={t("title")} lead={t("lead")} />
      <Section>
        {trades.length > 0 ? (
          <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {trades.map((trade) => (
              <li key={trade.slug}>
                <TradeCard trade={trade} />
              </li>
            ))}
          </ul>
        ) : (
          <>
            <p className="mb-6 text-lg text-ink-muted">{t("empty")}</p>
            <CtaPair />
          </>
        )}
      </Section>
      <HowSection rules={stats?.rules ?? null} tone="sand" />
      <ActionBar />
    </>
  );
}
