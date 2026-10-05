// /[metier]/[quartier] (ex. /plombier/ouakam). Question métier : « Un plombier vient-il chez moi, à
// Ouakam, et à quel prix de départ ? ». Action principale : « Faire une demande » (CTA double visible
// sans défilement, repris dans la barre fixe du mobile, avec « C'est urgent ? »).
//
// Existence : métier actif, zone active et métier ouvert dans la zone ; sinon 404 utile (jamais une
// page vide). Une panne de l'API n'est JAMAIS une 404 : elle remonte à error.tsx (500), pour ne pas
// faire désindexer la page. Indexation : seulement si le quartier a son texte d'intro (`indexable`) ;
// sinon `noindex, follow` et canonical vers elle-même. Rendu à la requête, données en cache 5 min.
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
import { buttonClass } from "@/components/ui/button";
import { localized } from "@/lib/requests/catalog";
import { getStats, getTrade, getTrades, getZone, getZoneTrades, getZones } from "@/lib/site/data";
import { availableProofs } from "@/lib/site/figures";
import {
  breadcrumbJsonLd,
  lowestPrice,
  organizationJsonLd,
  serviceJsonLd,
} from "@/lib/site/jsonld";
import { tradeZoneTitle, zoneLocative } from "@/lib/site/locative";
import { buildMetadata } from "@/lib/site/metadata";
import { SITE_PATHS, tradePath, tradeZonePath } from "@/lib/site/paths";
import { resolveSlug } from "@/lib/site/resolve";
import { absoluteUrl } from "@/lib/site/seo";
import { FALLBACK_SITE_ORIGIN, readSiteConfig } from "@/lib/site-config";

type Params = Promise<{ metier: string; quartier: string }>;

/** Lien du fil d'Ariane : cible de 48 px au moins. */
const crumb = "inline-flex min-h-12 items-center underline underline-offset-4";

/**
 * Paire canonique (métier, quartier) pour les deux segments : redirection 307 si l'un est un alias,
 * 404 si l'un est inconnu du catalogue. Rien n'est appelé en détail pour un slug inconnu.
 */
async function resolvePair(tradeParam: string, zoneParam: string) {
  const [trades, zones] = await Promise.all([getTrades(), getZones()]);
  const trade = resolveSlug(
    tradeParam,
    trades.map((item) => ({ slug: item.slug, aliases: item.aliases, names: [item.name.fr] })),
  );
  const zone = resolveSlug(
    zoneParam,
    zones.map((item) => ({ slug: item.slug, aliases: item.aliases, names: [item.name] })),
  );
  if (trade.kind === "unknown" || zone.kind === "unknown") notFound();
  if (trade.kind === "alias" || zone.kind === "alias") {
    redirect(tradeZonePath(trade.slug, zone.slug)); // 307 : les alias sont modifiables
  }
  return { tradeSlug: trade.slug, zoneSlug: zone.slug };
}

/** Données de la page, ou 404 si la paire n'est pas ouverte (métier fermé dans ce quartier). */
async function loadPair(tradeParam: string, zoneParam: string) {
  const { tradeSlug, zoneSlug } = await resolvePair(tradeParam, zoneParam);
  const [trade, zone] = await Promise.all([getTrade(tradeSlug), getZone(zoneSlug, tradeSlug)]);
  if (!trade || !zone || !trade.zones.includes(zoneSlug)) notFound();
  return { tradeSlug, zoneSlug, trade, zone };
}

export async function generateMetadata({ params }: { params: Params }): Promise<Metadata> {
  const { metier, quartier } = await params;
  const { tradeSlug, zoneSlug, trade, zone } = await loadPair(metier, quartier);
  const locale = await getLocale();
  const t = await getTranslations("site.tradeZone");
  const tSeo = await getTranslations("site.seo");
  const title = tradeZoneTitle(
    localized(trade.seo_title, locale),
    zoneLocative(
      { name: zone.name, locative: zone.locative },
      (name) => tSeo("locativeFallback", { name }),
      locale,
    ),
  );
  return buildMetadata({
    title,
    description: t("metaDescription", { title }),
    ogDescription: t("ogDescription", { title }),
    path: tradeZonePath(tradeSlug, zoneSlug),
    indexable: zone.indexable,
  });
}

export default async function TradeZonePage({ params }: { params: Params }) {
  const { metier, quartier } = await params;
  const { tradeSlug, zoneSlug, trade, zone } = await loadPair(metier, quartier);

  const t = await getTranslations("site.tradeZone");
  const tSite = await getTranslations("site");
  const locale = await getLocale();
  const { siteUrl, supportPhone } = readSiteConfig(process.env);
  const origin = siteUrl ?? FALLBACK_SITE_ORIGIN;

  const [zoneTrades, stats] = await Promise.all([
    getZoneTrades(zoneSlug),
    getStats({ trade: tradeSlug, zone: zoneSlug }),
  ]);
  const rules = stats?.rules ?? null;
  const proofs = availableProofs(stats);
  const tradeName = localized(trade.name, locale);
  const where = zoneLocative(
    { name: zone.name, locative: zone.locative },
    (name) => tSite("seo.locativeFallback", { name }),
    locale,
  );
  const title = tradeZoneTitle(localized(trade.seo_title, locale), where);
  const intro = zone.intro ? localized(zone.intro, locale) : t("introFallback");
  const services = trade.services.map((service) => ({
    slug: service.slug,
    name: localized(service.name, locale),
    priceFromXof: service.price_from_xof,
  }));
  const others = (zoneTrades ?? []).filter((item) => item.slug !== tradeSlug);
  const url = absoluteUrl(origin, tradeZonePath(tradeSlug, zoneSlug));
  const ctaProps = {
    trade: { slug: tradeSlug, name: tradeName },
    zone: { slug: zoneSlug, name: zone.name, locative: zone.locative },
  };

  return (
    <>
      <JsonLdScript
        data={serviceJsonLd({
          serviceType: tradeName,
          name: title,
          url,
          providerName: tSite("seo.siteName"),
          providerUrl: origin,
          area: { name: zone.name, city: capitalize(zone.city) },
          minPriceXof: lowestPrice(services.map((service) => service.priceFromXof)),
        })}
      />
      <JsonLdScript
        data={breadcrumbJsonLd([
          { name: tSite("seo.siteName"), url: absoluteUrl(origin, "/") },
          { name: tradeName, url: absoluteUrl(origin, tradePath(tradeSlug)) },
          { name: zone.name, url },
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

      <nav aria-label={t("breadcrumbLabel")} className="mx-auto max-w-6xl px-4 pt-4 sm:px-6">
        <ol className="flex flex-wrap items-center gap-x-2 text-sm text-ink-muted">
          <li>
            <Link href={SITE_PATHS.home} className={crumb}>
              {tSite("seo.siteName")}
            </Link>
          </li>
          <li aria-hidden="true">/</li>
          <li>
            <Link href={tradePath(tradeSlug)} className={crumb}>
              {tradeName}
            </Link>
          </li>
          <li aria-hidden="true">/</li>
          <li aria-current="page">{zone.name}</li>
        </ol>
      </nav>

      <PageHeader
        title={title}
        lead={intro}
        actions={<CtaPair {...ctaProps} urgentLink />}
        media={
          <TradeVisual
            iconKey={trade.icon_key}
            variant="compact"
            sizes="(min-width: 1024px) 560px, 100vw"
            eager
            className="h-full"
          />
        }
      />

      <Section title={tSite("trade.servicesTitle")}>
        <ServicesList tradeSlug={tradeSlug} zoneSlug={zoneSlug} services={services} />
      </Section>

      {proofs.length > 0 ? (
        <Section title={t("figuresTitle")} tone="sand">
          <div className="grid gap-10 sm:grid-cols-3">
            {proofs.slice(0, 3).map((figure) => (
              <StatFigure key={figure.kind} figure={figure} />
            ))}
          </div>
        </Section>
      ) : null}

      <HowSection rules={rules} tone={proofs.length > 0 ? "paper" : "sand"} />
      <WhenSection rules={rules} tone={proofs.length > 0 ? "sand" : "paper"} />

      {zone.nearby.length > 0 ? (
        <Section title={t("neighborsTitle", { trade: tradeName })}>
          <ul className="flex flex-wrap gap-3">
            {zone.nearby.map((near) => (
              <li key={near.slug}>
                <Link
                  href={tradeZonePath(tradeSlug, near.slug)}
                  className={buttonClass("secondary")}
                >
                  {near.name}
                </Link>
              </li>
            ))}
          </ul>
        </Section>
      ) : null}

      {others.length > 0 ? (
        <Section title={t("othersTitle", { where })} tone="sand">
          <ul className="flex flex-wrap gap-3">
            {others.map((other) => (
              <li key={other.slug}>
                <Link
                  href={tradeZonePath(other.slug, zoneSlug)}
                  className={buttonClass("secondary")}
                >
                  {localized(other.name, locale)}
                </Link>
              </li>
            ))}
          </ul>
        </Section>
      ) : null}

      <Section title={tSite("faq.title")}>
        <SiteFaq ids={SHORT_FAQ} rules={rules} />
      </Section>

      <Section title={t("supportTitle")} tone="sand">
        <p className="text-lg">{tSite("footer.hours")}</p>
        <div className="mt-6">
          <CtaPair {...ctaProps} noticeId="cta-notice-final" onSand />
        </div>
      </Section>
      <ActionBar {...ctaProps} />
    </>
  );
}

function capitalize(text: string): string {
  return text ? text.charAt(0).toUpperCase() + text.slice(1) : text;
}
