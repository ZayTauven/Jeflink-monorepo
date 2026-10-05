import type { Metadata } from "next";
import { Funnel_Display, Inter } from "next/font/google";
import { getLocale, getTranslations } from "next-intl/server";
import type { ReactNode } from "react";

import { FALLBACK_SITE_ORIGIN, readSiteConfig } from "@/lib/site-config";

import "./globals.css";

// Les polices du layout seulement (spec 006) : Funnel Display 600 et Inter 400/500/600, `latin` et
// `latin-ext` (ŋ, ë). `adjustFontFallback` est à `true` par défaut pour next/font/google : le repli
// système est ajusté aux métriques de la police, le titre se lit tout de suite sans saut.
const display = Funnel_Display({
  subsets: ["latin", "latin-ext"],
  weight: ["600"],
  variable: "--font-funnel-display",
  display: "swap",
});
const text = Inter({
  subsets: ["latin", "latin-ext"],
  weight: ["400", "500", "600"],
  variable: "--font-inter",
  display: "swap",
});

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("metadata");
  const { siteUrl, indexable } = readSiteConfig(process.env);
  return {
    // Base des URL absolues (canonical, Open Graph). Sans SITE_URL (dev, staging), une valeur
    // inoffensive : le site n'est de toute façon pas indexable.
    // Pas de lien « tel: » automatique : seuls nos numéros de service sont des liens (spec 006).
    formatDetection: { telephone: false },
    metadataBase: new URL(siteUrl ?? FALLBACK_SITE_ORIGIN),
    title: t("title"),
    description: t("description"),
    // `noindex` global tant que SITE_INDEXABLE n'est pas vrai (spec 006) ; robots.txt interdit tout.
    ...(indexable ? {} : { robots: { index: false, follow: false } }),
  };
}

// Ni NextIntlClientProvider ni Providers ici : chaque groupe de routes choisit ce qu'il envoie au
// navigateur. `(site)` : les messages de ses îlots seulement. `(espace)` : tout, avec React Query.
export default async function RootLayout({ children }: { children: ReactNode }) {
  const locale = await getLocale();
  return (
    <html lang={locale} className={`${display.variable} ${text.variable}`}>
      <body className="bg-paper font-sans text-ink antialiased">{children}</body>
    </html>
  );
}
