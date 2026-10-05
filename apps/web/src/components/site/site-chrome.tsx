// Cadre du site public : lien d'évitement, en-tête, `<main>`, pied de page, et les messages des
// seuls îlots client. Partagé par le layout `(site)` et par la 404 globale (hors groupe de routes).
// Une page publique ne lit jamais la session (ADR 0013) : les métiers viennent de `publicApi()`.
import { NextIntlClientProvider } from "next-intl";
import { getLocale, getMessages, getTranslations } from "next-intl/server";
import type { ReactNode } from "react";

import { type Messages, pickMessages, SITE_CLIENT_NAMESPACES } from "@/i18n/client-messages";
import { whatsappUrl } from "@/lib/login/support";
import { loadShellTrades } from "@/lib/site/shell-data";
import { readSiteConfig } from "@/lib/site-config";

import { SiteContextProvider } from "./site-context";
import { SiteFooter } from "./site-footer";
import { SiteHeader } from "./site-header";
import { SkipLink } from "./skip-link";

export async function SiteChrome({ children }: { children: ReactNode }) {
  const locale = await getLocale();
  const t = await getTranslations("site.footer");
  const { supportWhatsapp } = readSiteConfig(process.env);
  const trades = await loadShellTrades(locale);
  // Seuls les messages des îlots client partent au navigateur (menu, bandeau, erreur).
  const messages = pickMessages((await getMessages()) as Messages, SITE_CLIENT_NAMESPACES);
  return (
    <NextIntlClientProvider messages={messages}>
      <SiteContextProvider
        value={{ supportHref: whatsappUrl(supportWhatsapp, t("supportMessage")), trades }}
      >
        <SkipLink />
        <SiteHeader />
        <main id="contenu" tabIndex={-1} className="outline-none">
          {children}
        </main>
        <SiteFooter trades={trades} />
      </SiteContextProvider>
    </NextIntlClientProvider>
  );
}
