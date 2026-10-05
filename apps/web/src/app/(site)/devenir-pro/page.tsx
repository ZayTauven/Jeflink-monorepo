// /devenir-pro. Question métier : « Comment un artisan entre-t-il chez Jeflink, et que ça coûte quoi ? ».
// Action principale : « Je veux rejoindre Jeflink », un message vocal sur WhatsApp (Q10). Pas
// d'inscription en ligne : elle viendra avec l'app Pro. Dit sans détour : pas de frais d'entrée, pas
// d'abonnement, une commission par mission terminée, au taux affiché avant chaque devis (spec 005).
import type { Metadata } from "next";
import Image from "next/image";
import { getTranslations } from "next-intl/server";

import { SupportLink } from "@/components/support-link";
import { PageHeader, Section, ValueRows, VerifyList } from "@/components/site/sections";
import { SectionNumber } from "@/components/site/section-number";
import { composeWhatsappMessage } from "@/lib/site/whatsapp";
import { buildMetadata } from "@/lib/site/metadata";
import { SITE_PATHS } from "@/lib/site/paths";
import { SITE_IMAGES } from "@/lib/site/visuals";
import { readSiteConfig } from "@/lib/site-config";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("site.pro");
  return buildMetadata({
    title: t("metaTitle"),
    description: t("metaDescription"),
    path: SITE_PATHS.becomePro,
  });
}

export default async function BecomeProPage() {
  const t = await getTranslations("site.pro");
  const tSite = await getTranslations("site");
  const { supportWhatsapp } = readSiteConfig(process.env);
  const benefits = (["clients", "quote", "fees", "commission"] as const).map((id) => ({
    id,
    title: t(`benefits.${id}.title`),
    text: t(`benefits.${id}.text`),
  }));
  const steps = [t("steps.one"), t("steps.two"), t("steps.three")];
  const join = (
    <SupportLink
      number={supportWhatsapp}
      message={composeWhatsappMessage(t("joinMessage"), [])}
      label={t("join")}
      newTabLabel={tSite("newTab")}
      variant="primary"
    />
  );
  return (
    <>
      <PageHeader
        kicker={t("kicker")}
        title={t("title")}
        lead={t("lead")}
        actions={
          supportWhatsapp ? (
            <div className="flex flex-col items-start gap-2">
              {join}
              <p className="text-sm text-ink-muted">{t("note")}</p>
            </div>
          ) : (
            <p className="text-base text-ink-muted">{t("noNumber")}</p>
          )
        }
        media={
          <Image
            src={SITE_IMAGES.pro.image.src}
            width={SITE_IMAGES.pro.image.width}
            height={SITE_IMAGES.pro.image.height}
            sizes="(min-width: 1024px) 560px, 100vw"
            alt={tSite(`visuals.${SITE_IMAGES.pro.altKey}`)}
            loading="eager"
            fetchPriority="high"
            className="h-full w-full rounded-card object-cover"
          />
        }
      />

      <Section title={t("benefitsTitle")}>
        <ValueRows items={benefits} />
      </Section>

      <Section title={t("verifyTitle")} tone="sand">
        <div className="max-w-2xl">
          <VerifyList />
        </div>
      </Section>

      <Section title={t("stepsTitle")}>
        <ol className="grid gap-8 md:grid-cols-3">
          {steps.map((text, index) => (
            <li key={text} className="flex flex-col gap-3">
              <SectionNumber number={index + 1} />
              <p className="font-display text-2xl tracking-tight">{text}</p>
            </li>
          ))}
        </ol>
        {supportWhatsapp ? <div className="mt-10">{join}</div> : null}
      </Section>
    </>
  );
}
