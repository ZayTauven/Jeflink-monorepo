import type { Metadata } from "next";

import { CardGrid } from "@/console/cards";
import { consoleGet, type Query } from "@/console/data";
import { ZoneForm } from "@/console/forms";
import { Flash } from "@/console/kit";
import { Modal } from "@/console/modal";
import { plural } from "@/console/text";
import type { ZoneAdmin } from "@/console/types";
import { PageHead } from "@/console/ui";

export const metadata: Metadata = { title: "Quartiers" };

const BASE = "/console/quartiers";

export default async function ZonesPage({ searchParams }: { searchParams: Promise<Query> }) {
  const params = await searchParams;
  const zones = await consoleGet<ZoneAdmin[]>(BASE, "zones/");
  const served = zones.filter((z) => z.is_active).length;

  return (
    <>
      <PageHead
        title="Quartiers"
        subtitle={`${plural(served, "quartier desservi", "quartiers desservis")}. Fermer un quartier le retire des nouvelles demandes ; les demandes passées restent.`}
        actions={
          <Modal trigger="Ajouter un quartier" triggerClassName="ax-btn ax-btn--primary" title="Ajouter un quartier">
            <ZoneForm back={BASE} prefix="nouveau" />
          </Modal>
        }
      />
      <Flash ok={params.ok} erreur={params.erreur} />
      <CardGrid empty="Aucun quartier pour l'instant.">
        {zones.map((z) => (
          <article key={z.id} className="ax-card jf-item jf-item--compact" aria-label={z.name}>
            <div className="jf-item__head">
              <div className="jf-item__titles">
                <span className="ax-card__eyebrow">{z.city}</span>
                <h2 className="jf-item__title">{z.name}</h2>
              </div>
              <div className="jf-item__aside">
                <span
                  className={`jf-status ${z.is_active ? "jf-status--done" : "jf-status--cancelled"}`}
                >
                  {z.is_active ? "Desservi" : "Fermé"}
                </span>
              </div>
            </div>
            <div className="jf-item__foot">
              <dl className="jf-item__stats">
                <div>
                  <dt>Pros vérifiés</dt>
                  <dd className="ax-num">{z.pros_count}</dd>
                </div>
                <div>
                  <dt>Demandes (30 j)</dt>
                  <dd className="ax-num">{z.requests_30d}</dd>
                </div>
              </dl>
              <div className="jf-item__actions">
                <Modal trigger="Modifier" title="Modifier le quartier" subtitle={z.name}>
                  <ZoneForm zone={z} back={BASE} prefix={`zone-${z.id}`} />
                </Modal>
              </div>
            </div>
          </article>
        ))}
      </CardGrid>
    </>
  );
}
