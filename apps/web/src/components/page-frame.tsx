// Cadre visuel des pages du compte client, sans traduction ni accès serveur : utilisable par un
// Server Component (via PageShell) comme par une limite d'erreur, qui est un Client Component.
import Link from "next/link";
import type { ReactNode } from "react";

import { Logo } from "@/components/ui/logo";

export type PageFrameLabels = { home: string; nav: string; mine: string; new: string };

const link =
  "inline-flex min-h-12 items-center rounded-pill px-4 text-base font-medium text-ink " +
  "hover:bg-sand focus-visible:outline-2 focus-visible:outline-offset-2 " +
  "focus-visible:outline-accent-strong";

export function PageFrame({
  children,
  labels,
  width = "max-w-3xl",
}: {
  children: ReactNode;
  labels: PageFrameLabels;
  width?: string;
}) {
  return (
    <div className="min-h-dvh bg-paper">
      <header className="border-b border-line bg-surface">
        <div className="mx-auto flex max-w-5xl flex-wrap items-center justify-between gap-x-6 px-4 py-2 sm:px-6">
          <Link href="/" aria-label={labels.home} className="inline-flex min-h-12 items-center">
            <Logo />
          </Link>
          <nav aria-label={labels.nav} className="flex flex-wrap items-center gap-1">
            <Link href="/compte/demandes" className={link}>
              {labels.mine}
            </Link>
            <Link href="/demande" className={link}>
              {labels.new}
            </Link>
          </nav>
        </div>
      </header>
      <main className={`mx-auto w-full px-4 pb-16 pt-8 sm:px-6 sm:pt-12 ${width}`}>{children}</main>
    </div>
  );
}
