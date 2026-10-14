import type { Metadata } from "next";

import { CardGrid } from "@/console/cards";
import { consoleGet, type Query } from "@/console/data";
import { CityForm, ZoneForm } from "@/console/forms";
import { Flash } from "@/console/kit";
import { Modal } from "@/console/modal";
import { plural } from "@/console/text";
import type { CityAdmin, ZoneAdmin } from "@/console/types";
import { PageHead } from "@/console/ui";

export const metadata: Metadata = { title: "Villes et quartiers" };

const BASE = "/console/quartiers";

export default async function ZonesPage({ searchParams }: { searchParams: Promise<Query> }) {
  const params = await searchParams;
  const [cities, zones] = await Promise.all([
    consoleGet<CityAdmin[]>(BASE, "cities/"),
    consoleGet<ZoneAdmin[]>(BASE, "zones/"),
  ]);
  const open = cities.filter((c) => c.is_active);
  const served = zones.filter((z) => z.is_active && open.some((c) => c.id === z.city_id)).length;

  return (
    <>
      <PageHead
        title="Villes et quartiers"
        subtitle={`${plural(open.length, "ville ouverte", "villes ouvertes")}, ${plural(served, "quartier desservi", "quartiers desservis")}. Fermer une ville ou un quartier le retire des nouvelles demandes ; les demandes passées restent.`}
        actions={
          <>
            <Modal
              trigger="Ajouter une ville"
              triggerClassName="ax-btn ax-btn--secondary"
              title="Ajouter une ville"
              subtitle="Elle reste fermée tant que vous ne l'ouvrez pas."
            >
              <CityForm back={BASE} prefix="ville" />
            </Modal>
            <Modal
              trigger="Ajouter un quartier"
              triggerClassName="ax-btn ax-btn--primary"
              title="Ajouter un quartier"
            >
              <ZoneForm cities={cities} back={BASE} prefix="nouveau" />
            </Modal>
          </>
        }
      />
      <Flash ok={params.ok} erreur={params.erreur} />

      {cities.map((city) => {
        const own = zones.filter((z) => z.city_id === city.id);
        return (
          <section key={city.id} className="jf-city" aria-labelledby={`ville-${city.id}`}>
            <div className="jf-city__head">
              <div>
                <h2 id={`ville-${city.id}`} className="jf-section-title jf-city__title">
                  {city.name}
                </h2>
                <span className="jf-sub">
                  Région de {city.region_label} ·{" "}
                  {plural(city.zones_open, "quartier ouvert", "quartiers ouverts")} sur{" "}
                  {city.zones_count}
                </span>
              </div>
              <div className="jf-inline">
                <span
                  className={`jf-status ${city.is_active ? "jf-status--done" : "jf-status--cancelled"}`}
                >
                  {city.is_active ? "Ouverte" : "Fermée"}
                </span>
                <Modal trigger="Modifier la ville" title="Modifier la ville" subtitle={city.name}>
                  <CityForm city={city} back={BASE} prefix={`ville-${city.id}`} />
                </Modal>
              </div>
            </div>
            <CardGrid empty="Aucun quartier dans cette ville pour l'instant.">
              {own.map((z) => (
                <article
                  key={z.id}
                  className="ax-card jf-item jf-item--compact"
                  aria-label={z.name}
                >
                  <div className="jf-item__head">
                    <div className="jf-item__titles">
                      <span className="ax-card__eyebrow">{z.city}</span>
                      <h3 className="jf-item__title">{z.name}</h3>
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
                        <ZoneForm zone={z} cities={cities} back={BASE} prefix={`zone-${z.id}`} />
                      </Modal>
                    </div>
                  </div>
                </article>
              ))}
            </CardGrid>
          </section>
        );
      })}
    </>
  );
}
