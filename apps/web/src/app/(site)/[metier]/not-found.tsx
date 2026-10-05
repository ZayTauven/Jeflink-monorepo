// 404 d'un métier inconnu, fermé ou inactif (spec 006, web 6) : jamais une page vide. Une panne de
// l'API n'arrive jamais ici : elle passe par error.tsx (500), pour ne pas faire désindexer la page.
import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";

import { NotFoundView } from "@/components/site/not-found-view";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("site.notFound");
  return { title: t("metaTitle"), robots: { index: false, follow: true } };
}

export default function TradeNotFound() {
  return <NotFoundView />;
}
