/** Blocs partagés entre plusieurs rubriques de la console (litige, ligne de demande…). */
import Link from "next/link";

import { ActionForm } from "./kit";
import { Submit } from "./submit";
import { ago } from "./text";
import type { DisputeRow, DisputeStatus, RequestRow } from "./types";
import { Status } from "./ui";
import { formatDate, formatXOF } from "@/lib/format";

const DISPUTE_CLASS: Record<DisputeStatus, string> = {
  open: "jf-status--open",
  investigating: "jf-status--booked",
  resolved: "jf-status--done",
  dismissed: "jf-status--cancelled",
};

export function DisputeStatusPill({ status, label }: { status: DisputeStatus; label: string }) {
  return <span className={`jf-status ${DISPUTE_CLASS[status]}`}>{label}</span>;
}

/** Un litige : les faits, les deux parties, la décision ; et le formulaire pour avancer. */
export function DisputeCard({
  dispute: d,
  back,
  showRequest = true,
}: {
  dispute: DisputeRow;
  back: string;
  showRequest?: boolean;
}) {
  const closed = d.status === "resolved" || d.status === "dismissed";
  return (
    <section className="ax-card jf-dispute" aria-label={`Litige ${d.id}`}>
      <div className="ax-card__header">
        <div className="ax-card__titles">
          <span className="ax-card__eyebrow">
            Litige n° {d.id} · ouvert {ago(d.created_at)} par {d.opened_by.name}
          </span>
          <h2 className="ax-card__title">{d.reason_label}</h2>
          {showRequest && (
            <p className="ax-card__subtitle">
              <Link href={`/console/demandes/${d.request.id}`} className="jf-link">
                #{d.request.id} {d.request.title}
              </Link>
            </p>
          )}
        </div>
        <div className="ax-card__actions">
          <DisputeStatusPill status={d.status} label={d.status_label} />
        </div>
      </div>
      <div className="ax-card__body" style={{ paddingTop: 0 }}>
        <p className="jf-prose">« {d.description} »</p>
        <div className="jf-parties">
          <Party role="Client" person={d.client} href={`/console/clients/${d.client.id}`} />
          {d.pro && <Party role="Pro" person={d.pro} href={`/console/pros/${d.pro.id}`} />}
        </div>
        {d.resolution && (
          <p className="jf-decision">
            <strong>Décision&nbsp;:</strong> {d.resolution}
            {d.handled_by && (
              <span className="jf-sub">
                {d.handled_by.name}
                {d.closed_at && ` · ${formatDate(d.closed_at, true)}`}
              </span>
            )}
          </p>
        )}
        {!closed && (
          <ActionForm
            endpoint={`/api/console/disputes/${d.id}/status/`}
            back={back}
            ok="Litige mis à jour."
            className="jf-dispute__form"
          >
            <div className="ax-field">
              <label className="ax-field__label" htmlFor={`status-${d.id}`}>
                Nouvel état
              </label>
              <select
                id={`status-${d.id}`}
                name="status"
                className="ax-select"
                defaultValue={d.status === "open" ? "investigating" : "resolved"}
              >
                <option value="investigating">En cours (on enquête)</option>
                <option value="resolved">Résolu</option>
                <option value="dismissed">Sans suite</option>
              </select>
            </div>
            <div className="ax-field">
              <label className="ax-field__label" htmlFor={`resolution-${d.id}`}>
                Décision (obligatoire pour clore, visible du client et du pro)
              </label>
              <textarea
                id={`resolution-${d.id}`}
                name="resolution"
                className="ax-textarea"
                rows={2}
                maxLength={2000}
                defaultValue={d.resolution}
                placeholder="Ex. : le pro repasse gratuitement samedi matin."
              />
            </div>
            <Submit className="ax-btn ax-btn--primary ax-btn--sm">Mettre à jour</Submit>
          </ActionForm>
        )}
      </div>
    </section>
  );
}

function Party({
  role,
  person,
  href,
}: {
  role: string;
  person: DisputeRow["client"];
  href: string;
}) {
  return (
    <div className="jf-party">
      <span className="jf-sub">{role}</span>
      <Link href={href} className="jf-link jf-strong">
        {person.name}
      </Link>
      {person.phone && (
        <a href={`tel:${person.phone}`} className="jf-sub">
          <i className="bi bi-telephone" aria-hidden="true" /> {person.phone}
        </a>
      )}
    </div>
  );
}

/** Tableau compact de demandes (fiches pro et client). */
export function RequestTable({ rows, empty }: { rows: RequestRow[]; empty: string }) {
  if (rows.length === 0) return <p className="jf-muted">{empty}</p>;
  return (
    <div className="ax-table-wrap">
      <table className="ax-table ax-table--compact ax-table--hover">
        <thead>
          <tr>
            <th scope="col">Demande</th>
            <th scope="col" style={{ textAlign: "end" }}>
              Montant
            </th>
            <th scope="col">Statut</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id}>
              <td>
                <Link href={`/console/demandes/${r.id}`} className="jf-link">
                  #{r.id} {r.title}
                </Link>
                <span className="jf-sub">
                  {r.trade.name} · {r.zone.name} · {ago(r.created_at)}
                </span>
              </td>
              <td className="ax-num jf-nowrap" style={{ textAlign: "end" }}>
                {r.amount === null ? "—" : formatXOF(r.amount)}
              </td>
              <td>
                <Status status={r.status} label={r.status_label} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
