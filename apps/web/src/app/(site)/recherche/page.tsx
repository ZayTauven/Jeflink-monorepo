// /recherche?metier=&quartier= . Question métier : « Mon quartier a-t-il une page, et laquelle ? ».
// Rendu par le serveur, sans JS. Quatre issues, jamais un cul-de-sac :
// - une égalité (« PA », « Parcelles ») : redirection 307 vers /[metier]/[quartier] ;
// - des préfixes (« Sacré ») : les quartiers proposés, en liens ;
// - une zone connue où le métier n'est pas ouvert : « Pas encore de … » et les métiers ouverts ;
// - rien (« Gorée ») : WhatsApp et « Autre quartier ».
// Le texte tapé ne sort pas de la requête : ni journal, ni recopie dans une page, un lien ou le
// message WhatsApp (il pourrait contenir une adresse ou un numéro). Page `noindex`.
import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";
import { getLocale, getTranslations } from "next-intl/server";

import { PageHeader, Section } from "@/components/site/sections";
import { ZoneSearchForm } from "@/components/site/zone-search-form";
import { SupportLink } from "@/components/support-link";
import { buttonClass } from "@/components/ui/button";
import { localized } from "@/lib/requests/catalog";
import { getTrade, getTrades, getZoneTrades, getZones } from "@/lib/site/data";
import { zoneLocative } from "@/lib/site/locative";
import { demandPath, SITE_PATHS, tradePath, tradeZonePath } from "@/lib/site/paths";
import { cleanQuery, searchZones } from "@/lib/site/zone-search";
import { readSiteConfig } from "@/lib/site-config";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("site.recherche");
  const tSeo = await getTranslations("site.seo");
  return {
    title: { absolute: tSeo("titleTemplate", { title: t("metaTitle") }) },
    robots: { index: false, follow: false },
  };
}

type SearchParams = Promise<Record<string, string | string[] | undefined>>;

export default async function SearchPage({ searchParams }: { searchParams: SearchParams }) {
  const params = await searchParams;
  const query = cleanQuery(params.quartier);
  const metierParam = cleanQuery(params.metier);

  const t = await getTranslations("site.recherche");
  const tSite = await getTranslations("site");
  const locale = await getLocale();
  const { supportWhatsapp } = readSiteConfig(process.env);

  // Le métier vient d'un slug validé contre le catalogue ; sinon ignoré, sans bruit.
  const trades = await getTrades();
  const tradeSlug = trades.find((trade) => trade.slug === metierParam)?.slug ?? null;
  const trade = tradeSlug ? await getTrade(tradeSlug) : null;
  const zones = await getZones();
  const outcome = searchZones(
    query,
    zones.map((zone) => ({ slug: zone.slug, name: zone.name, aliases: zone.aliases })),
    trade ? new Set(trade.zones) : null,
  );

  if (outcome.kind === "exact" && tradeSlug) {
    redirect(tradeZonePath(tradeSlug, outcome.zone.slug)); // 307 : le texte tapé ne reste pas dans l'URL
  }

  const where = (name: string) =>
    zoneLocative({ name }, (zoneName) => tSite("seo.locativeFallback", { name: zoneName }), locale);

  // Métiers à proposer dans un quartier : sans métier (égalité) ou métier fermé (zone connue).
  const zoneForTrades = outcome.kind === "exact" || outcome.kind === "closed" ? outcome.zone : null;
  const zoneTrades = zoneForTrades ? ((await getZoneTrades(zoneForTrades.slug)) ?? []) : [];

  const whatsappMessage = t("whatsappMessage");
  const tradeName = trade ? localized(trade.name, locale) : "";

  return (
    <>
      <PageHeader
        kicker={tSite("search.label")}
        title={
          outcome.kind === "closed" && zoneForTrades
            ? t("closedTitle", { trade: tradeName, where: where(zoneForTrades.name) })
            : outcome.kind === "suggest"
              ? t("suggestionsTitle")
              : outcome.kind === "exact" && zoneForTrades
                ? t("tradeChoiceTitle", { where: where(zoneForTrades.name) })
                : t("noneTitle")
        }
        {...(outcome.kind === "closed"
          ? { lead: t("closedText") }
          : outcome.kind === "none"
            ? { lead: t("noneText") }
            : {})}
      />
      <Section>
        {outcome.kind === "suggest" ? (
          <ul className="flex flex-wrap gap-3">
            {outcome.zones.map((zone) => (
              <li key={zone.slug}>
                <Link
                  href={
                    tradeSlug
                      ? tradeZonePath(tradeSlug, zone.slug)
                      : demandPath({ quartier: zone.slug })
                  }
                  className={buttonClass("secondary")}
                >
                  {zone.name}
                </Link>
              </li>
            ))}
          </ul>
        ) : null}

        {zoneTrades.length > 0 ? (
          <ul className="flex flex-wrap gap-3">
            {zoneTrades.map((item) => (
              <li key={item.slug}>
                <Link
                  href={
                    zoneForTrades
                      ? tradeZonePath(item.slug, zoneForTrades.slug)
                      : tradePath(item.slug)
                  }
                  className={buttonClass("secondary")}
                >
                  {localized(item.name, locale)}
                </Link>
              </li>
            ))}
          </ul>
        ) : null}

        {outcome.kind === "none" || outcome.kind === "closed" ? (
          <div className="mt-8 flex flex-col items-start gap-3 sm:flex-row">
            <SupportLink
              number={supportWhatsapp}
              message={whatsappMessage}
              label={t("whatsapp")}
              newTabLabel={tSite("newTab")}
              variant="primary"
            />
            <Link href={demandPath({ metier: tradeSlug })} className={buttonClass("secondary")}>
              {t("otherZone")}
            </Link>
          </div>
        ) : null}

        <div className="mt-12 border-t border-line pt-8">
          <ZoneSearchForm tradeSlug={tradeSlug} />
          {tradeSlug ? (
            <p className="mt-6">
              <Link href={tradePath(tradeSlug)} className={buttonClass("quiet", "px-0!")}>
                {t("backToTrade")}
              </Link>
            </p>
          ) : (
            <p className="mt-6">
              <Link href={SITE_PATHS.trades} className={buttonClass("quiet", "px-0!")}>
                {tSite("home.tradesLink")}
              </Link>
            </p>
          )}
        </div>
      </Section>
    </>
  );
}
