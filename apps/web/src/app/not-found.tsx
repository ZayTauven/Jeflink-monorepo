// 404 globale du site (spec 006, web 12). Question métier : « Cette page n'existe pas : où aller ? ».
// Jamais un cul-de-sac : champ « Votre quartier », métiers (si le cache les a), WhatsApp, accueil.
// Hors groupe de routes : elle reprend le cadre public elle-même. Le 404 propre au métier viendra
// avec la page métier (web 6).
import type { Metadata } from "next";
import { getLocale, getTranslations } from "next-intl/server";

import { RecoveryPanel } from "@/components/site/recovery-panel";
import { SiteChrome } from "@/components/site/site-chrome";
import { whatsappUrl } from "@/lib/login/support";
import { loadShellTrades } from "@/lib/site/shell-data";
import { readSiteConfig } from "@/lib/site-config";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("site.notFound");
  return { title: t("metaTitle"), robots: { index: false, follow: true } };
}

export default async function NotFound() {
  const t = await getTranslations("site.notFound");
  const tSearch = await getTranslations("site.search");
  const tFooter = await getTranslations("site.footer");
  const tSite = await getTranslations("site");
  const locale = await getLocale();
  const { supportWhatsapp } = readSiteConfig(process.env);
  const trades = await loadShellTrades(locale);
  return (
    <SiteChrome>
      <RecoveryPanel
        labels={{
          title: t("title"),
          lead: t("lead"),
          tradesTitle: t("tradesTitle"),
          whatsappLead: t("whatsappLead"),
          whatsapp: t("whatsapp"),
          newTab: tSite("newTab"),
          home: t("home"),
          search: {
            label: tSearch("label"),
            example: tSearch("example"),
            submit: tSearch("submit"),
          },
        }}
        trades={trades}
        supportHref={whatsappUrl(supportWhatsapp, tFooter("supportMessage"))}
      />
    </SiteChrome>
  );
}
