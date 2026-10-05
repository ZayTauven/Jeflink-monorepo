// /a-propos. Question métier : « Pourquoi faire confiance à Jeflink ? ». Action principale :
// faire une demande (CTA double en bas). Composition : titre en deux blocs, phrase centrée,
// rangées de points forts, chiffres vrais, Dakar, carte « Vous êtes artisan ? » (spec 006).
// Aucune photo d'équipe ni témoignage. États : sans `stats` (API en panne), seuls les chiffres
// vrais par construction s'affichent ; sous les seuils, aucune preuve.
import type { Metadata } from "next";
import Image from "next/image";
import Link from "next/link";
import { getTranslations } from "next-intl/server";

import { CtaPair } from "@/components/site/cta-pair";
import { Section, PageHeader, ValueRows, VerifyList } from "@/components/site/sections";
import { StatFigure } from "@/components/site/stat-figure";
import { buttonClass } from "@/components/ui/button";
import { chooseFigures } from "@/lib/site/figures";
import { getStats } from "@/lib/site/data";
import { buildMetadata } from "@/lib/site/metadata";
import { SITE_PATHS } from "@/lib/site/paths";
import { SITE_IMAGES } from "@/lib/site/visuals";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("site.about");
  return buildMetadata({
    title: t("metaTitle"),
    description: t("metaDescription"),
    path: SITE_PATHS.about,
  });
}

export default async function AboutPage() {
  const t = await getTranslations("site.about");
  const tVisual = await getTranslations("site.visuals");
  const stats = await getStats();
  const figures = chooseFigures(stats);
  const reasons = (["price", "verified", "proofs"] as const).map((id) => ({
    id,
    title: t(`reasons.${id}.title`),
    text: t(`reasons.${id}.text`),
  }));
  return (
    <>
      <PageHeader
        title={t("title")}
        lead={t("lead")}
        media={
          <Image
            src={SITE_IMAGES.dakar.image.src}
            width={SITE_IMAGES.dakar.image.width}
            height={SITE_IMAGES.dakar.image.height}
            sizes="(min-width: 1024px) 560px, 100vw"
            alt={tVisual(SITE_IMAGES.dakar.altKey)}
            loading="eager"
            fetchPriority="high"
            className="h-full w-full rounded-card object-cover"
          />
        }
      />

      <Section tone="sand">
        <p className="mx-auto max-w-3xl text-balance text-center font-display text-3xl leading-[1.1] tracking-tight sm:text-5xl">
          {t("statement")}
        </p>
      </Section>

      <Section title={t("reasonsTitle")}>
        <ValueRows items={reasons} />
      </Section>

      <Section title={t("verifyTitle")} tone="sand">
        <div className="max-w-2xl">
          <VerifyList />
        </div>
      </Section>

      <Section title={t("figuresTitle")}>
        <div className="grid gap-10 sm:grid-cols-3">
          {figures.map((figure) => (
            <StatFigure key={figure.kind} figure={figure} />
          ))}
        </div>
      </Section>

      <Section title={t("dakarTitle")} lead={t("dakarText")} tone="sand" />

      <Section>
        <div className="flex flex-col items-start gap-4 rounded-card border border-line bg-surface p-6 sm:p-10">
          <h2 className="font-display text-3xl tracking-tight sm:text-4xl">{t("proTitle")}</h2>
          <p className="text-lg text-ink-muted">{t("proText")}</p>
          <Link href={SITE_PATHS.becomePro} className={buttonClass("secondary")}>
            {t("proLink")}
          </Link>
        </div>
      </Section>

      <Section title={t("ctaTitle")} tone="sand">
        <CtaPair />
      </Section>
    </>
  );
}
