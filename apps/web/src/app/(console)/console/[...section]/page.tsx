import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { findNavItem, NAV } from "@/console/nav";
import { PageHead } from "@/console/ui";
import { redirect } from "next/navigation";

import { requireStaff } from "@/lib/api";

type Props = { params: Promise<{ section: string[] }> };

/** Rubrique prévue mais pas encore construite : on dit ce qu'elle fera et dans quel lot. */
export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const item = findNavItem(`/console/${(await params).section[0]}`);
  return { title: item?.label ?? "Introuvable" };
}

export default async function PlannedSection({ params }: Props) {
  // Chaque page de la console vérifie l'accès, pas seulement le layout.
  const { me } = await requireStaff("/console");
  const item = findNavItem(`/console/${(await params).section[0]}`);
  if (!item?.lot) notFound();
  const section = item.section ?? NAV.find((s) => s.items.includes(item))?.section;
  if (section && !me.console_sections.includes(section)) {
    redirect(
      `/console?erreur=${encodeURIComponent("Cette rubrique n'est pas ouverte à votre rôle.")}`,
    );
  }

  return (
    <>
      <PageHead title={item.label} />
      <section className="ax-card jf-soon-hero">
        <div className="ax-card__body">
          <span className="jf-kpi-icon mb-4" aria-hidden="true">
            <i className={`bi ${item.icon}`} />
          </span>
          <p className="ax-card__eyebrow">Pas encore disponible · prévu au lot {item.lot}</p>
          <p className="mt-2 mb-6 text-base" style={{ color: "var(--ax-text)" }}>
            {item.summary}
          </p>
          <Link href="/console" className="ax-btn ax-btn--primary">
            Retour au tableau de bord
          </Link>
        </div>
      </section>
    </>
  );
}
