/** Journal d'audit : lien vers la cible d'une action et extrait pour une fiche. */
import Link from "next/link";

import { consoleGet } from "./data";
import { ago } from "./text";
import type { AuditRow, Page } from "./types";
import { Card } from "./ui";

export function targetHref(row: Pick<AuditRow, "target_type" | "target_id">): string | null {
  switch (row.target_type) {
    case "pro":
      return `/console/pros/${row.target_id}`;
    case "client":
      return `/console/clients/${row.target_id}`;
    case "request":
      return `/console/demandes/${row.target_id}`;
    case "review":
      return "/console/avis";
    case "contact":
      return "/console/messages";
    case "dispute":
      return "/console/litiges?etat=tous";
    default:
      return null;
  }
}

/** Les dernières actions de l'équipe sur une fiche (pro, client). */
export async function AuditTrail({
  here,
  target,
  id,
}: {
  here: string;
  target: string;
  id: number;
}) {
  const data = await consoleGet<Page<AuditRow>>(here, "audit/", {
    target_type: target,
    target_id: String(id),
  });
  return (
    <Card title="Journal" eyebrow="Actions de l'équipe">
      {data.results.length === 0 ? (
        <p className="jf-muted">Aucune action de l&apos;équipe sur cette fiche.</p>
      ) : (
        <ul className="ax-list ax-list--compact">
          {data.results.slice(0, 8).map((row) => (
            <li key={row.id} className="ax-list__row">
              <span className="ax-list__content">
                <span className="ax-list__title">{row.action_label}</span>
                <span className="ax-list__meta">
                  {row.details && `${row.details} · `}
                  {row.actor?.name ?? "Équipe"} · {ago(row.created_at)}
                </span>
              </span>
            </li>
          ))}
        </ul>
      )}
      {data.count > 8 && (
        <Link href={`/console/journal?cible=${target}&id=${id}`} className="jf-link">
          Tout le journal de cette fiche →
        </Link>
      )}
    </Card>
  );
}
