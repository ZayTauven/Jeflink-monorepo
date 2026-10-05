import { getTranslations } from "next-intl/server";

import { ActionBar } from "@/components/site/action-bar";
import { CtaPair } from "@/components/site/cta-pair";

// Accueil provisoire (web 1) : le socle du site public autour du contenu d'avant. Les sections de
// l'accueil Crafto arrivent avec web 5 (spec 006).
export default async function HomePage() {
  const t = await getTranslations("home");
  return (
    <>
      <div className="mx-auto max-w-3xl px-6 py-24">
        <h1 className="font-display text-5xl leading-[1.05] tracking-tight">{t("title")}</h1>
        <p className="mt-6 text-lg text-ink-muted">{t("lead")}</p>
        <CtaPair className="mt-10" />
      </div>
      <ActionBar />
    </>
  );
}
