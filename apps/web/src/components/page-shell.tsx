// Cadre des pages du compte client (demande, mes demandes) : logo, deux liens, contenu.
// Rendu serveur ; aucune donnée de session ici. Une limite d'erreur (Client Component) utilise
// PageFrame directement, avec useTranslations.
import { getTranslations } from "next-intl/server";
import type { ReactNode } from "react";

import { PageFrame } from "@/components/page-frame";

export async function PageShell({
  children,
  width = "max-w-3xl",
}: {
  children: ReactNode;
  width?: string;
}) {
  const t = await getTranslations("requests.shell");
  const tBrand = await getTranslations("brand");
  return (
    <PageFrame
      width={width}
      labels={{ home: tBrand("home"), nav: t("nav"), mine: t("mine"), new: t("new") }}
    >
      {children}
    </PageFrame>
  );
}
