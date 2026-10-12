import type { Metadata } from "next";
import Link from "next/link";

import { CardGrid, RequestCard } from "@/console/cards";
import { consoleGet, type Query } from "@/console/data";
import { Flash, Pager, Tabs } from "@/console/kit";
import type { Page, RequestRow } from "@/console/types";
import { PageHead } from "@/console/ui";
import { getTrades, getZones } from "@/lib/api";

export const metadata: Metadata = { title: "Demandes" };

const BASE = "/console/demandes";

export default async function RequestsPage({ searchParams }: { searchParams: Promise<Query> }) {
  const params = await searchParams;
  const [data, trades, zones] = await Promise.all([
    consoleGet<Page<RequestRow>>(BASE, "requests/", {
      status: params.statut,
      trade: params.metier,
      zone: params.quartier,
      q: params.q,
      urgent: params.urgent,
      stale: params.sans_devis,
      dispute: params.litige,
      page: params.page,
    }),
    getTrades(),
    getZones(),
  ]);
  const f = data.facets;
  const total = Object.values(f).reduce((a, b) => a + b, 0);

  return (
    <>
      <PageHead
        title="Demandes"
        subtitle="Toutes les demandes des clients, à chaque étape. Ouvrez une demande pour voir ses devis, son historique et agir."
      />
      <Flash ok={params.ok} erreur={params.erreur} />
      <Tabs
        base={BASE}
        params={params}
        name="statut"
        label="Statut"
        tabs={[
          { value: "", label: "Toutes", count: total },
          { value: "open", label: "En attente de devis", count: f.open ?? 0 },
          { value: "booked", label: "Pro réservé", count: f.booked ?? 0 },
          { value: "done", label: "Terminées", count: f.done ?? 0 },
          { value: "cancelled", label: "Annulées", count: f.cancelled ?? 0 },
        ]}
      />

      <form className="jf-filters" method="get" action={BASE} role="search">
        {params.statut && <input type="hidden" name="statut" value={params.statut} />}
        <div className="ax-field">
          <label className="ax-field__label" htmlFor="q">
            Rechercher
          </label>
          <input
            id="q"
            name="q"
            className="ax-input"
            defaultValue={params.q}
            placeholder="N°, titre, client ou pro"
          />
        </div>
        <div className="ax-field">
          <label className="ax-field__label" htmlFor="metier">
            Métier
          </label>
          <select
            id="metier"
            name="metier"
            className="ax-select"
            defaultValue={params.metier ?? ""}
          >
            <option value="">Tous</option>
            {trades.map((t) => (
              <option key={t.slug} value={t.slug}>
                {t.name}
              </option>
            ))}
          </select>
        </div>
        <div className="ax-field">
          <label className="ax-field__label" htmlFor="quartier">
            Quartier
          </label>
          <select
            id="quartier"
            name="quartier"
            className="ax-select"
            defaultValue={params.quartier ?? ""}
          >
            <option value="">Tous</option>
            {zones.map((z) => (
              <option key={z.slug} value={z.slug}>
                {z.name}
              </option>
            ))}
          </select>
        </div>
        <fieldset className="jf-checks">
          <legend className="ax-field__label">Afficher seulement</legend>
          <label>
            <input type="checkbox" name="urgent" value="1" defaultChecked={params.urgent === "1"} />{" "}
            Urgentes
          </label>
          <label>
            <input
              type="checkbox"
              name="sans_devis"
              value="1"
              defaultChecked={params.sans_devis === "1"}
            />{" "}
            Sans devis, à relancer
          </label>
          <label>
            <input type="checkbox" name="litige" value="1" defaultChecked={params.litige === "1"} />{" "}
            Avec un litige en cours
          </label>
        </fieldset>
        <div className="jf-filters__actions">
          <button type="submit" className="ax-btn ax-btn--primary">
            Filtrer
          </button>
          <Link href={BASE} className="ax-btn ax-btn--ghost">
            Effacer
          </Link>
        </div>
      </form>

      <CardGrid empty="Aucune demande ne correspond à ces filtres.">
        {data.results.map((r) => (
          <RequestCard key={r.id} r={r} />
        ))}
      </CardGrid>
      <Pager count={data.count} base={BASE} params={params} />
    </>
  );
}
