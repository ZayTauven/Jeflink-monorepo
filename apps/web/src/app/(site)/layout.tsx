// Site public : en-tête, contenu, pied de page. Une page de ce groupe ne lit jamais la session
// (ni cookies, ni en-têtes du visiteur) : son HTML est le même pour tous (ADR 0013). Les données
// passent par `publicApi()`, jamais par `serverApi()` (test d'architecture, web 2).
import { NextIntlClientProvider } from "next-intl";
import { getMessages } from "next-intl/server";
import type { ReactNode } from "react";

import { SiteFooter } from "@/components/site/site-footer";
import { SiteHeader } from "@/components/site/site-header";
import { SkipLink } from "@/components/site/skip-link";
import { type Messages, pickMessages, SITE_CLIENT_NAMESPACES } from "@/i18n/client-messages";

export default async function SiteLayout({ children }: { children: ReactNode }) {
  // Seuls les messages des îlots client partent au navigateur (menu mobile, pause du bandeau).
  const messages = pickMessages((await getMessages()) as Messages, SITE_CLIENT_NAMESPACES);
  return (
    <NextIntlClientProvider messages={messages}>
      <SkipLink />
      <SiteHeader />
      <main id="contenu" tabIndex={-1} className="outline-none">
        {children}
      </main>
      <SiteFooter />
    </NextIntlClientProvider>
  );
}
