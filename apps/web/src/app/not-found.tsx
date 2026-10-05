// 404 globale du site (spec 006, web 12). Question métier : « Cette page n'existe pas : où aller ? ».
// Jamais un cul-de-sac : champ « Votre quartier », métiers (si le cache les a), WhatsApp, accueil.
// Hors groupe de routes : elle reprend le cadre public elle-même.
import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";

import { NotFoundView } from "@/components/site/not-found-view";
import { SiteChrome } from "@/components/site/site-chrome";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("site.notFound");
  return { title: t("metaTitle"), robots: { index: false, follow: true } };
}

export default function NotFound() {
  return (
    <SiteChrome>
      <NotFoundView />
    </SiteChrome>
  );
}
