// Cadre des pages du compte client (demande, mes demandes) : logo, deux liens, contenu.
// Rendu serveur ; aucune donnée de session ici.
import Link from "next/link";
import { getTranslations } from "next-intl/server";
import type { ReactNode } from "react";

import { Logo } from "@/components/ui/logo";

export async function PageShell({
  children,
  width = "max-w-3xl",
}: {
  children: ReactNode;
  width?: string;
}) {
  const t = await getTranslations("requests.shell");
  const tBrand = await getTranslations("brand");
  const link =
    "inline-flex min-h-12 items-center rounded-pill px-4 text-base font-medium text-ink " +
    "hover:bg-sand focus-visible:outline-2 focus-visible:outline-offset-2 " +
    "focus-visible:outline-accent-strong";
  return (
    <div className="min-h-dvh bg-paper">
      <header className="border-b border-line bg-surface">
        <div className="mx-auto flex max-w-5xl flex-wrap items-center justify-between gap-x-6 px-4 py-2 sm:px-6">
          <Link href="/" aria-label={tBrand("home")} className="inline-flex min-h-12 items-center">
            <Logo />
          </Link>
          <nav aria-label={t("nav")} className="flex flex-wrap items-center gap-1">
            <Link href="/compte/demandes" className={link}>
              {t("mine")}
            </Link>
            <Link href="/demande" className={link}>
              {t("new")}
            </Link>
          </nav>
        </div>
      </header>
      <main className={`mx-auto w-full px-4 pb-16 pt-8 sm:px-6 sm:pt-12 ${width}`}>{children}</main>
    </div>
  );
}
