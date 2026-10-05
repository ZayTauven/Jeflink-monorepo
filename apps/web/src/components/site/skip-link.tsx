// Lien d'évitement : premier élément focusable de chaque page publique, visible au focus seulement.
import { getTranslations } from "next-intl/server";

import { SITE_PATHS } from "@/lib/site/paths";

export async function SkipLink() {
  const t = await getTranslations("site");
  return (
    <a
      href={SITE_PATHS.content}
      className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-50 focus:inline-flex focus:min-h-12 focus:items-center focus:rounded-pill focus:bg-ink focus:px-6 focus:text-base focus:font-medium focus:text-paper focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
    >
      {t("skip")}
    </a>
  );
}
