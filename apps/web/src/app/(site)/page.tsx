// Accueil. Question métier : « Quel pro, pour quoi, et combien de temps avant d'avoir un prix ? ».
// Action principale : « Faire une demande » (CTA double : WhatsApp au même rang). Ordre (spec 006,
// Crafto marketing-strategy) : hero, bandeau des métiers, comment ça marche, métiers, quartiers,
// garanties et chiffres, ce qu'on vérifie et ne demande jamais, carte artisan, FAQ, bandeau final.
// États : sans catalogue (API en panne, aucune copie) les sections de données sont remplacées par
// le CTA WhatsApp ; un chiffre sous son seuil n'est pas rendu ; jamais de texte posé sur une photo.
import type { Metadata } from "next";
import Image from "next/image";
import Link from "next/link";
import { getLocale, getTranslations } from "next-intl/server";

import { ActionBar } from "@/components/site/action-bar";
import { CtaPair } from "@/components/site/cta-pair";
import { JsonLdScript } from "@/components/site/json-ld";
import { Marquee } from "@/components/site/marquee";
import {
  GuaranteesList,
  HowSection,
  NeverList,
  Section,
  VerifyList,
  WhenSection,
} from "@/components/site/sections";
import { FULL_FAQ, SiteFaq } from "@/components/site/site-faq";
import { StatFigure } from "@/components/site/stat-figure";
import { TradeCard } from "@/components/site/trade-card";
import { TradeLabel } from "@/components/site/trade-label";
import { TradeVisual } from "@/components/site/trade-visual";
import { SupportLink } from "@/components/support-link";
import { buttonClass } from "@/components/ui/button";
import { whatsappUrl } from "@/lib/login/support";
import { localized } from "@/lib/requests/catalog";
import { getStats, getTrades, getZones, softly } from "@/lib/site/data";
import { chooseFigures } from "@/lib/site/figures";
import { organizationJsonLd, websiteJsonLd } from "@/lib/site/jsonld";
import { buildMetadata } from "@/lib/site/metadata";
import { SITE_PATHS, tradePath } from "@/lib/site/paths";
import { absoluteUrl } from "@/lib/site/seo";
import { SITE_IMAGES } from "@/lib/site/visuals";
import { FALLBACK_SITE_ORIGIN, readSiteConfig } from "@/lib/site-config";
import { ZoneSearchForm } from "@/components/site/zone-search-form";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("metadata");
  const tSeo = await getTranslations("site.seo");
  const meta = await buildMetadata({
    title: t("title"),
    description: t("description"),
    ogDescription: tSeo("ogHome"),
    path: SITE_PATHS.home,
  });
  // Le titre de l'accueil est déjà complet (« Jeflink · … ») : pas de suffixe de marque.
  return { ...meta, title: { absolute: t("title") } };
}

export default async function HomePage() {
  const t = await getTranslations("site.home");
  const tHome = await getTranslations("home");
  const tSite = await getTranslations("site");
  const tVisual = await getTranslations("site.visuals");
  const locale = await getLocale();
  const { supportWhatsapp, supportPhone, siteUrl } = readSiteConfig(process.env);
  const origin = siteUrl ?? FALLBACK_SITE_ORIGIN;

  const [tradeList, zones, stats] = await Promise.all([
    softly(getTrades),
    softly(getZones),
    getStats(),
  ]);
  const rules = stats?.rules ?? null;
  const trades = tradeList.map((trade) => ({
    slug: trade.slug,
    name: localized(trade.name, locale),
    iconKey: trade.icon_key,
    description: trade.short_description ? localized(trade.short_description, locale) : null,
  }));
  const figures = chooseFigures(stats);
  const photoTrade = trades.find((trade) => trade.iconKey && trade.iconKey !== "appliance");
  const whatsapp = whatsappUrl(supportWhatsapp, t("zonesWhatsapp"));

  return (
    <>
      <JsonLdScript
        data={organizationJsonLd({
          name: tSite("seo.siteName"),
          url: origin,
          description: tSite("seo.orgDescription"),
          phone: supportPhone,
        })}
      />
      <JsonLdScript
        data={websiteJsonLd({ name: tSite("seo.siteName"), url: absoluteUrl(origin, "/") })}
      />

      <section className="mx-auto max-w-6xl px-4 pb-8 pt-6 sm:px-6 sm:pt-10">
        <div className="grid gap-4 lg:grid-cols-[3fr_2fr]">
          <div className="flex flex-col justify-between gap-8 rounded-card border border-line bg-surface p-6 sm:p-10">
            <div>
              <h1 className="font-display text-balance text-5xl leading-[1.02] tracking-tight sm:text-7xl">
                {tHome("title")}
              </h1>
              <p className="mt-5 max-w-xl text-lg text-ink-muted">
                {rules ? t("lead", { count: rules.max_quotes_per_request }) : t("leadNoRules")}
              </p>
              <CtaPair className="mt-8" />
            </div>
            {trades.length > 0 ? (
              <nav aria-label={t("chipsLabel")}>
                <ul className="flex flex-wrap gap-2">
                  {trades.map((trade) => (
                    <li key={trade.slug}>
                      <Link
                        href={tradePath(trade.slug)}
                        className="inline-flex min-h-12 items-center rounded-pill border border-line-strong bg-paper px-4 hover:border-ink focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-strong"
                      >
                        <TradeLabel iconKey={trade.iconKey} label={trade.name} size="sm" />
                      </Link>
                    </li>
                  ))}
                </ul>
              </nav>
            ) : null}
          </div>
          <Image
            src={SITE_IMAGES.hero.large.src}
            width={SITE_IMAGES.hero.large.width}
            height={SITE_IMAGES.hero.large.height}
            sizes="(min-width: 1024px) 40vw, 100vw"
            alt={tVisual(SITE_IMAGES.hero.altKey)}
            preload
            className="h-72 w-full rounded-card object-cover sm:h-96 lg:h-full"
          />
        </div>
      </section>

      {trades.length > 0 ? (
        <Section tone="paper" className="overflow-hidden">
          <Marquee items={trades.map((trade) => trade.name)} />
        </Section>
      ) : null}

      <HowSection rules={rules} tone="sand" />
      <WhenSection rules={rules} />

      {trades.length > 0 ? (
        <Section id="metiers" title={t("tradesTitle")} lead={t("tradesLead")} tone="sand">
          <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {trades.map((trade) => (
              <li key={trade.slug}>
                <TradeCard trade={trade} />
              </li>
            ))}
          </ul>
          <p className="mt-8">
            <Link href={SITE_PATHS.trades} className={buttonClass("secondary")}>
              {t("tradesLink")}
            </Link>
          </p>
        </Section>
      ) : (
        <Section title={t("tradesTitle")} tone="sand">
          <p className="mb-6 text-lg text-ink-muted">{tSite("trades.empty")}</p>
          <CtaPair />
        </Section>
      )}

      {zones.length > 0 ? (
        <Section id="quartiers" title={t("zonesTitle")} lead={t("zonesLead")}>
          <ul className="flex flex-wrap gap-x-6 gap-y-2 text-lg">
            {zones.map((zone) => (
              <li key={zone.slug}>{zone.name}</li>
            ))}
          </ul>
          <ZoneSearchForm className="mt-8" />
          <div className="mt-8 flex flex-col items-start gap-3">
            <p className="text-base text-ink-muted">{t("zonesMissing")}</p>
            {whatsapp ? (
              <SupportLink
                number={supportWhatsapp}
                message={t("zonesWhatsapp")}
                label={t("zonesWhatsapp")}
                newTabLabel={tSite("newTab")}
              />
            ) : null}
          </div>
        </Section>
      ) : null}

      <Section title={tSite("guarantees.title")} tone="sand">
        <div className="grid gap-4 lg:grid-cols-2">
          {photoTrade ? (
            <TradeVisual
              iconKey={photoTrade.iconKey}
              sizes="(min-width: 1024px) 560px, 100vw"
              className="h-full"
            />
          ) : null}
          <div className="flex flex-col items-start gap-6 rounded-card border border-line bg-surface p-6 sm:p-8">
            <GuaranteesList rules={rules} />
            <Link href={SITE_PATHS.about} className={buttonClass("secondary")}>
              {tSite("guarantees.link")}
            </Link>
          </div>
        </div>
        <div className="mt-12 grid gap-10 sm:grid-cols-3">
          {figures.map((figure) => (
            <StatFigure key={figure.kind} figure={figure} />
          ))}
        </div>
      </Section>

      <Section>
        <div className="grid gap-10 lg:grid-cols-2">
          <div>
            <h2 className="font-display text-3xl tracking-tight sm:text-4xl">
              {tSite("about.verifyTitle")}
            </h2>
            <div className="mt-6">
              <VerifyList />
            </div>
          </div>
          <div>
            <h2 className="font-display text-3xl tracking-tight sm:text-4xl">
              {tSite("never.title")}
            </h2>
            <div className="mt-6">
              <NeverList />
            </div>
          </div>
        </div>
      </Section>

      <Section tone="sand">
        <div className="grid items-center gap-6 rounded-card border border-line bg-surface p-3 md:grid-cols-2">
          <Image
            src={SITE_IMAGES.pro.image.src}
            width={SITE_IMAGES.pro.image.width}
            height={SITE_IMAGES.pro.image.height}
            sizes="(min-width: 768px) 45vw, 100vw"
            alt={tVisual(SITE_IMAGES.pro.altKey)}
            loading="lazy"
            className="h-auto w-full rounded-card object-cover"
          />
          <div className="flex flex-col items-start gap-4 p-3 sm:p-6">
            <h2 className="font-display text-3xl tracking-tight sm:text-4xl">{t("proTitle")}</h2>
            <p className="text-lg text-ink-muted">{t("proText")}</p>
            <Link href={SITE_PATHS.becomePro} className={buttonClass("secondary")}>
              {t("proLink")}
            </Link>
          </div>
        </div>
      </Section>

      <Section title={tSite("faq.title")}>
        <SiteFaq ids={FULL_FAQ} rules={rules} />
      </Section>

      <Section title={t("finalTitle")} tone="sand">
        <CtaPair noticeId="cta-notice-final" />
      </Section>
      <ActionBar />
    </>
  );
}
