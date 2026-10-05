// /[metier] (ex. /plombier). Question métier : « Ce métier couvre-t-il mon problème, à quel prix de
// départ, et dans mon quartier ? ». Action principale : « Faire une demande » (CTA double, repris
// dans la barre fixe du mobile). Contenu : intro du métier, services et prix, quartiers ouverts en
// liens, champ « Votre quartier » (GET, sans JS), comment ça marche, quand le pro vient, FAQ.
// URL : un mot égal à un alias redirige en 307 vers le slug ; `notFound()` seulement sur une vraie
// absence (slug inconnu du catalogue, ou `trade_not_found`) ; une panne de l'API remonte à error.tsx.
import type { Metadata } from "next";
import Link from "next/link";
import { notFound, redirect } from "next/navigation";
import { getLocale, getTranslations } from "next-intl/server";

import { ActionBar } from "@/components/site/action-bar";
import { CtaPair } from "@/components/site/cta-pair";
import { JsonLdScript } from "@/components/site/json-ld";
import { HowSection, PageHeader, Section, WhenSection } from "@/components/site/sections";
import { ServicesList } from "@/components/site/services-list";
import { SiteFaq } from "@/components/site/site-faq";
import { SHORT_FAQ } from "@/lib/site/faq-rules";
import { StatFigure } from "@/components/site/stat-figure";
import { TradeVisual } from "@/components/site/trade-visual";
import { ZoneSearchForm } from "@/components/site/zone-search-form";
import { buttonClass } from "@/components/ui/button";
import { localized } from "@/lib/requests/catalog";
import { getStats, getTrade, getTrades, getZones } from "@/lib/site/data";
import { availableProofs } from "@/lib/site/figures";
import {
  breadcrumbJsonLd,
  lowestPrice,
  organizationJsonLd,
  serviceJsonLd,
} from "@/lib/site/jsonld";
import { buildMetadata } from "@/lib/site/metadata";
import { tradePath, tradeZonePath } from "@/lib/site/paths";
import { resolveSlug } from "@/lib/site/resolve";
import { absoluteUrl } from "@/lib/site/seo";
import { FALLBACK_SITE_ORIGIN, readSiteConfig } from "@/lib/site-config";

type Params = Promise<{ metier: string }>;

/** Slug canonique du segment, ou redirection (alias) / 404 (inconnu). Validé avant tout appel de détail. */
async function resolveTrade(param: string): Promise<string> {
  const trades = await getTrades();
  const hit = resolveSlug(
    param,
    trades.map((trade) => ({ slug: trade.slug, aliases: trade.aliases, names: [trade.name.fr] })),
  );
  if (hit.kind === "unknown") notFound();
  if (hit.kind === "alias") redirect(tradePath(hit.slug)); // 307 : les alias sont modifiables
  return hit.slug;
}

export async function generateMetadata({ params }: { params: Params }): Promise<Metadata> {
  const { metier } = await params;
  const slug = await resolveTrade(metier);
  const trade = await getTrade(slug);
  if (!trade) return {};
  const locale = await getLocale();
  const t = await getTranslations("site.trade");
  const title = localized(trade.seo_title, locale);
  return buildMetadata({
    title,
    description: t("metaDescription", { title }),
    ogDescription: t("ogDescription", { title }),
    path: tradePath(slug),
  });
}

export default async function TradePage({ params }: { params: Params }) {
  const { metier } = await params;
  const slug = await resolveTrade(metier);
  const trade = await getTrade(slug);
  if (!trade) notFound();

  const t = await getTranslations("site.trade");
  const tSite = await getTranslations("site");
  const locale = await getLocale();
  const { siteUrl, supportPhone } = readSiteConfig(process.env);
  const origin = siteUrl ?? FALLBACK_SITE_ORIGIN;

  const [zones, stats] = await Promise.all([getZones(), getStats({ trade: slug })]);
  const rules = stats?.rules ?? null;
  const proofs = availableProofs(stats);
  const name = localized(trade.name, locale);
  const title = localized(trade.seo_title, locale);
  const intro = trade.seo_intro
    ? localized(trade.seo_intro, locale)
    : trade.short_description
      ? localized(trade.short_description, locale)
      : undefined;
  const zoneNames = new Map(zones.map((zone) => [zone.slug, zone.name]));
  const openZones = trade.zones.flatMap((zoneSlug) => {
    const zoneName = zoneNames.get(zoneSlug);
    return zoneName ? [{ slug: zoneSlug, name: zoneName }] : [];
  });
  const services = trade.services.map((service) => ({
    slug: service.slug,
    name: localized(service.name, locale),
    priceFromXof: service.price_from_xof,
  }));
  const url = absoluteUrl(origin, tradePath(slug));
  const ctaTrade = { slug, name };

  return (
    <>
      <JsonLdScript
        data={serviceJsonLd({
          serviceType: name,
          name: title,
          url,
          providerName: tSite("seo.siteName"),
          providerUrl: origin,
          minPriceXof: lowestPrice(services.map((service) => service.priceFromXof)),
        })}
      />
      <JsonLdScript
        data={breadcrumbJsonLd([
          { name: tSite("seo.siteName"), url: absoluteUrl(origin, "/") },
          { name, url },
        ])}
      />
      <JsonLdScript
        data={organizationJsonLd({
          name: tSite("seo.siteName"),
          url: origin,
          description: tSite("seo.orgDescription"),
          phone: supportPhone,
        })}
      />

      <PageHeader
        title={title}
        {...(intro ? { lead: intro } : {})}
        actions={<CtaPair trade={ctaTrade} />}
        media={
          <TradeVisual
            iconKey={trade.icon_key}
            sizes="(min-width: 1024px) 560px, 100vw"
            eager
            className="h-full"
          />
        }
      />

      <Section title={t("servicesTitle")}>
        <ServicesList tradeSlug={slug} services={services} />
      </Section>

      <Section title={t("zonesTitle")} tone="sand">
        {openZones.length > 0 ? (
          <ul className="flex flex-wrap gap-3">
            {openZones.map((zone) => (
              <li key={zone.slug}>
                <Link href={tradeZonePath(slug, zone.slug)} className={buttonClass("secondary")}>
                  {zone.name}
                </Link>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-lg text-ink-muted">{t("zonesEmpty")}</p>
        )}
        <div className="mt-10">
          <h3 className="font-display text-2xl tracking-tight">{t("searchTitle")}</h3>
          <ZoneSearchForm tradeSlug={slug} className="mt-4" />
        </div>
      </Section>

      {proofs.length > 0 ? (
        <Section>
          <div className="grid gap-10 sm:grid-cols-3">
            {proofs.slice(0, 3).map((figure) => (
              <StatFigure key={figure.kind} figure={figure} />
            ))}
          </div>
        </Section>
      ) : null}

      <HowSection rules={rules} tone="sand" />
      <WhenSection rules={rules} />

      <Section title={tSite("faq.title")} tone="sand">
        <SiteFaq ids={SHORT_FAQ} rules={rules} />
      </Section>

      <Section>
        <CtaPair trade={ctaTrade} noticeId="cta-notice-final" />
      </Section>
      <ActionBar trade={ctaTrade} />
    </>
  );
}
