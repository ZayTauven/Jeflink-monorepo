// Contenu de la 404 du site (globale ou propre au métier) : champ « Votre quartier », métiers du
// cache (si l'API les a), WhatsApp, accueil. Server Component ; la 404 globale l'enveloppe dans
// le cadre public, celle du métier est déjà dans le layout `(site)`.
import { getLocale, getTranslations } from "next-intl/server";

import { whatsappUrl } from "@/lib/login/support";
import { loadShellTrades } from "@/lib/site/shell-data";
import { readSiteConfig } from "@/lib/site-config";

import { RecoveryPanel } from "./recovery-panel";

export async function NotFoundView() {
  const t = await getTranslations("site.notFound");
  const tSearch = await getTranslations("site.search");
  const tFooter = await getTranslations("site.footer");
  const tSite = await getTranslations("site");
  const locale = await getLocale();
  const { supportWhatsapp } = readSiteConfig(process.env);
  const trades = await loadShellTrades(locale);
  return (
    <RecoveryPanel
      labels={{
        title: t("title"),
        lead: t("lead"),
        tradesTitle: t("tradesTitle"),
        whatsappLead: t("whatsappLead"),
        whatsapp: t("whatsapp"),
        newTab: tSite("newTab"),
        home: t("home"),
        search: { label: tSearch("label"), example: tSearch("example"), submit: tSearch("submit") },
      }}
      trades={trades}
      supportHref={whatsappUrl(supportWhatsapp, tFooter("supportMessage"))}
    />
  );
}
