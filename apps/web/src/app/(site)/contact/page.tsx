// /contact. Question métier : « Comment joindre Jeflink, et est-ce bien Jeflink ? ». Action
// principale : écrire sur WhatsApp. Pas de formulaire en V1 (Q4) : aucune donnée collectée, aucun
// endpoint. Sans numéro configuré, les boutons n'apparaissent pas (dev) ; la demande reste proposée.
import type { Metadata } from "next";
import Link from "next/link";
import { getTranslations } from "next-intl/server";

import { PageHeader, Section } from "@/components/site/sections";
import { buttonClass } from "@/components/ui/button";
import { CallIcon, ChatIcon, ClockIcon } from "@/components/ui/icons";
import { whatsappUrl } from "@/lib/login/support";
import { formatPhoneDisplay } from "@/lib/requests/format";
import { buildMetadata } from "@/lib/site/metadata";
import { demandPath, SITE_PATHS } from "@/lib/site/paths";
import { readSiteConfig } from "@/lib/site-config";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("site.contact");
  return buildMetadata({
    title: t("metaTitle"),
    description: t("metaDescription"),
    path: SITE_PATHS.contact,
  });
}

const bigLink =
  "flex min-h-24 items-center gap-4 rounded-card border border-line bg-surface p-6 " +
  "hover:border-ink focus-visible:outline-2 focus-visible:outline-offset-2 " +
  "focus-visible:outline-accent-strong";

export default async function ContactPage() {
  const t = await getTranslations("site.contact");
  const tSite = await getTranslations("site");
  const { supportWhatsapp, supportPhone } = readSiteConfig(process.env);
  const whatsapp = whatsappUrl(supportWhatsapp, tSite("footer.supportMessage"));
  return (
    <>
      <PageHeader kicker={t("kicker")} title={t("title")} lead={t("lead")} />
      <Section>
        <div className="grid gap-4 md:grid-cols-2">
          {whatsapp && supportWhatsapp ? (
            <a href={whatsapp} target="_blank" rel="noopener noreferrer" className={bigLink}>
              <ChatIcon className="size-8 shrink-0 text-accent-strong" />
              <span>
                <span className="block font-display text-2xl">{tSite("footer.whatsapp")}</span>
                <span className="block text-base text-ink-muted">
                  {formatPhoneDisplay(`+${supportWhatsapp}`)}
                </span>
                <span className="block text-sm text-ink-muted">{t("whatsappHint")}</span>
                <span className="sr-only"> {tSite("newTab")}</span>
              </span>
            </a>
          ) : null}
          {supportPhone ? (
            <a href={`tel:${supportPhone}`} className={bigLink}>
              <CallIcon className="size-8 shrink-0 text-accent-strong" />
              <span>
                <span className="block font-display text-2xl">{t("callTitle")}</span>
                <span className="block text-base text-ink-muted">
                  {formatPhoneDisplay(supportPhone)}
                </span>
              </span>
            </a>
          ) : null}
        </div>
        {!whatsapp && !supportPhone ? (
          <p className="text-lg text-ink-muted">{t("noNumber")}</p>
        ) : null}

        <div className="mt-10 flex items-start gap-3">
          <ClockIcon className="mt-1 size-6 shrink-0 text-accent-strong" />
          <div>
            <h2 className="font-display text-2xl tracking-tight">{t("hoursTitle")}</h2>
            <p className="mt-1 text-base">{tSite("footer.hours")}</p>
            <p className="mt-1 text-base text-ink-muted">{tSite("footer.onlyNumbers")}</p>
          </div>
        </div>
      </Section>

      <Section title={t("requestTitle")} lead={t("requestText")} tone="sand">
        <Link href={demandPath()} className={buttonClass("primary")}>
          {tSite("cta.request")}
        </Link>
      </Section>
    </>
  );
}
