import type { Metadata } from "next";
import Link from "next/link";

import { ActivityChart } from "@/console/charts";
import type { Overview } from "@/console/types";
import { ago, plural } from "@/console/text";
import { Flash } from "@/console/kit";
import { Card, Delta, Empty, Kpi, PageHead, PeriodSwitch, Status } from "@/console/ui";
import { api, requireStaff } from "@/lib/api";
import { formatRating, formatXOF } from "@/lib/format";

export const metadata: Metadata = { title: "Tableau de bord" };

const PERIODS = [7, 30, 90];

export default async function DashboardPage({
  searchParams,
}: {
  searchParams: Promise<{ jours?: string; erreur?: string }>;
}) {
  const { jours, erreur } = await searchParams;
  const days = PERIODS.includes(Number(jours)) ? Number(jours) : 30;
  const { me, token } = await requireStaff("/console");
  const ops = me.console_sections.includes("operations");
  const res = await api<Overview>(`/api/console/overview/?days=${days}`, { token });

  if (!res.ok) {
    return (
      <>
        <PageHead title="Tableau de bord" />
        <div className="ax-alert ax-alert--danger" role="alert">
          {res.error || "Les chiffres ne sont pas disponibles."}
        </div>
      </>
    );
  }

  const o = res.data;
  const { current: now, previous: before, counts, alerts } = o;
  const maxTrade = Math.max(1, ...o.by_trade.map((t) => t.requests));
  const maxZone = Math.max(1, ...o.by_zone.map((z) => z.requests));
  const periodTotal = o.status_breakdown.reduce((n, s) => n + s.count, 0);

  return (
    <>
      <PageHead
        title="Tableau de bord"
        subtitle={`Activité de la plateforme sur les ${days} derniers jours, comparée aux ${days} jours d'avant.`}
        actions={<PeriodSwitch days={days} base="/console" />}
      />
      <Flash erreur={erreur} />

      <div className="ax-dash-grid">
        <Kpi
          label="Demandes publiées"
          icon="bi-inbox"
          dark
          value={now.requests.toLocaleString("fr-FR")}
          delta={<Delta now={now.requests} before={before.requests} />}
          foot={`${plural(counts.open_requests, "demande", "demandes")} en attente de devis aujourd'hui`}
        />
        <Kpi
          label="Taux de réservation"
          icon="bi-patch-check"
          value={now.booking_rate === null ? "—" : String(now.booking_rate)}
          unit={now.booking_rate === null ? undefined : "%"}
          delta={<Delta now={now.booking_rate} before={before.booking_rate} unit="pts" />}
          foot="Demandes de la période qui ont trouvé un pro"
        />
        <Kpi
          label="Volume d'affaires"
          icon="bi-cash-coin"
          value={now.volume.toLocaleString("fr-FR")}
          unit="F CFA"
          delta={<Delta now={now.volume} before={before.volume} />}
          foot="Devis acceptés pendant la période"
        />
        <Kpi
          label="Note moyenne"
          icon="bi-star-half"
          value={formatRating(now.rating)}
          unit={now.rating === null ? undefined : "/ 5"}
          delta={<Delta now={now.rating} before={before.rating} unit="pts" />}
          foot={`${plural(now.reviews, "avis laissé", "avis laissés")}`}
        />

        <Card
          className={ops ? "ax-col--8" : "ax-col--12"}
          eyebrow="Activité"
          title="Demandes et réservations"
          subtitle={days > 31 ? "Par semaine, heure de Dakar" : "Par jour, heure de Dakar"}
        >
          <ActivityChart daily={o.daily} />
        </Card>

        {ops && (
          <Card
            className="ax-col--4 jf-col-md-full"
            eyebrow="À traiter"
            title="Ce qui attend l'équipe"
          >
            <ul className="ax-list ax-list--compact">
              {alerts.pending_pros.map((p) => (
                <li key={`pro-${p.id}`} className="ax-list__row">
                  <span className="ax-list__leading">
                    <span className="jf-kpi-icon" aria-hidden="true">
                      <i className="bi bi-person-badge" />
                    </span>
                  </span>
                  <span className="ax-list__content">
                    <Link className="ax-list__title" href={`/console/pros/${p.id}`}>
                      {p.name} attend sa vérification
                    </Link>
                    <span className="ax-list__meta">
                      {p.trades.join(", ") || "Métier non renseigné"} · inscrit {ago(p.joined_at)}
                    </span>
                  </span>
                </li>
              ))}
              {alerts.stale_requests.map((r) => (
                <li key={`req-${r.id}`} className="ax-list__row">
                  <span className="ax-list__leading">
                    <span className="jf-kpi-icon" aria-hidden="true">
                      <i className="bi bi-hourglass-split" />
                    </span>
                  </span>
                  <span className="ax-list__content">
                    <Link className="ax-list__title" href={`/console/demandes/${r.id}`}>
                      {r.title} : aucun devis
                    </Link>
                    <span className="ax-list__meta">
                      {r.trade} · {r.zone} · publiée {ago(r.created_at)}
                    </span>
                  </span>
                </li>
              ))}
              {alerts.low_reviews.map((r) => (
                <li key={`rev-${r.request_id}`} className="ax-list__row">
                  <span className="ax-list__leading">
                    <span className="jf-kpi-icon" aria-hidden="true">
                      <i className="bi bi-star-half" />
                    </span>
                  </span>
                  <span className="ax-list__content">
                    <Link className="ax-list__title" href="/console/avis?vue=basses">
                      Avis {r.rating}/5 pour {r.pro?.name ?? "un pro"}
                    </Link>
                    <span className="ax-list__meta">
                      {r.comment ? `« ${r.comment} »` : "Sans commentaire"} · {ago(r.created_at)}
                    </span>
                  </span>
                </li>
              ))}
              {counts.contact_unhandled > 0 && (
                <li className="ax-list__row">
                  <span className="ax-list__leading">
                    <span className="jf-kpi-icon" aria-hidden="true">
                      <i className="bi bi-chat-left-text" />
                    </span>
                  </span>
                  <span className="ax-list__content">
                    <Link className="ax-list__title" href="/console/messages">
                      {plural(
                        counts.contact_unhandled,
                        "message de contact à lire",
                        "messages de contact à lire",
                      )}
                    </Link>
                  </span>
                </li>
              )}
            </ul>
            {alerts.pending_pros.length +
              alerts.stale_requests.length +
              alerts.low_reviews.length +
              counts.contact_unhandled ===
              0 && (
              <Empty>Rien en attente : aucun pro à vérifier, aucune demande sans devis.</Empty>
            )}
          </Card>
        )}

        <Card
          className="ax-col--7"
          eyebrow="Catalogue"
          title="Demandes par métier"
          subtitle="Nombre de demandes et volume réservé sur la période"
        >
          <div className="ax-table-wrap">
            <table className="ax-table ax-table--compact">
              <thead>
                <tr>
                  <th scope="col">Métier</th>
                  <th scope="col">Demandes</th>
                  <th scope="col" style={{ textAlign: "end" }}>
                    Volume
                  </th>
                </tr>
              </thead>
              <tbody>
                {o.by_trade.map((t) => (
                  <tr key={t.slug}>
                    <td>
                      <i className={`bi ${t.icon} me-2`} aria-hidden="true" />
                      {t.name}
                    </td>
                    <td style={{ minWidth: 160 }}>
                      <div className="flex items-center gap-3">
                        <div className="jf-bar flex-1" aria-hidden="true">
                          <span style={{ width: `${(t.requests / maxTrade) * 100}%` }} />
                        </div>
                        <span className="ax-num">{t.requests}</span>
                      </div>
                    </td>
                    <td className="ax-num" style={{ textAlign: "end" }}>
                      {formatXOF(t.volume)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>

        <Card
          className="ax-col--5 jf-col-md-full"
          eyebrow="Pros"
          title="Meilleurs pros de la période"
          subtitle="Classés par volume réservé"
        >
          {o.top_pros.length === 0 ? (
            <Empty>Aucune réservation sur la période.</Empty>
          ) : (
            <ul className="ax-list ax-list--compact">
              {o.top_pros.map((p, i) => (
                <li key={p.id} className="ax-list__row">
                  <span className="ax-list__leading">
                    {p.photo ? (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img className="ax-avatar" src={p.photo} alt="" width={40} height={40} />
                    ) : (
                      <span className="jf-initials">{i + 1}</span>
                    )}
                  </span>
                  <span className="ax-list__content">
                    <span className="ax-list__title">{p.name}</span>
                    <span className="ax-list__meta">
                      {p.trades.join(", ")} · {plural(p.missions, "mission", "missions")} ·{" "}
                      {p.rating.average === null
                        ? "pas encore noté"
                        : `${formatRating(p.rating.average)}/5 (${p.rating.count} avis)`}
                    </span>
                  </span>
                  <span className="ax-list__trailing ax-num">{formatXOF(p.volume)}</span>
                </li>
              ))}
            </ul>
          )}
        </Card>

        <Card className="ax-col--4" eyebrow="Cycle" title="Statut des demandes de la période">
          <ul className="ax-list ax-list--compact">
            {o.status_breakdown.map((s) => (
              <li key={s.status} className="ax-list__row">
                <span className="ax-list__content">
                  <Status status={s.status} label={s.label} />
                </span>
                <span className="ax-list__trailing ax-num">
                  {s.count}
                  <small style={{ color: "var(--ax-text-subtle)" }}>
                    {" "}
                    · {periodTotal ? Math.round((s.count / periodTotal) * 100) : 0} %
                  </small>
                </span>
              </li>
            ))}
          </ul>
          <dl className="mt-4 grid grid-cols-2 gap-3 text-sm">
            <div>
              <dt style={{ color: "var(--ax-text-muted)" }}>1er devis en moyenne</dt>
              <dd className="ax-num font-semibold">
                {now.first_quote_hours === null
                  ? "—"
                  : `${now.first_quote_hours.toLocaleString("fr-FR")} h`}
              </dd>
            </div>
            <div>
              <dt style={{ color: "var(--ax-text-muted)" }}>Pros vérifiés</dt>
              <dd className="ax-num font-semibold">
                {counts.pros_verified} / {counts.pros}
              </dd>
            </div>
            <div>
              <dt style={{ color: "var(--ax-text-muted)" }}>Clients inscrits</dt>
              <dd className="ax-num font-semibold">{counts.clients}</dd>
            </div>
            <div>
              <dt style={{ color: "var(--ax-text-muted)" }}>Pros à vérifier</dt>
              <dd className="ax-num font-semibold">{counts.pros_pending}</dd>
            </div>
          </dl>
        </Card>

        <Card className="ax-col--4" eyebrow="Zones" title="Quartiers les plus demandés">
          {o.by_zone.length === 0 ? (
            <Empty>Aucune demande sur la période.</Empty>
          ) : (
            <ul className="ax-list ax-list--compact">
              {o.by_zone.map((z) => (
                <li key={z.slug} className="ax-list__row">
                  <span className="ax-list__content">
                    <span className="ax-list__title">{z.name}</span>
                    <div className="jf-bar mt-1" aria-hidden="true">
                      <span
                        style={{
                          width: `${(z.requests / maxZone) * 100}%`,
                          background: "var(--ax-chart-2)",
                        }}
                      />
                    </div>
                  </span>
                  <span className="ax-list__trailing ax-num">{z.requests}</span>
                </li>
              ))}
            </ul>
          )}
        </Card>

        <Card className="ax-col--4 jf-col-md-full" eyebrow="Journal" title="Activité récente">
          <ul className="ax-list ax-list--compact">
            {o.activity.map((e) => (
              <li key={e.id} className="ax-list__row">
                <span className="ax-list__content">
                  <Link className="ax-list__title" href={`/console/demandes/${e.request_id}`}>
                    {e.title}
                  </Link>
                  <span className="ax-list__meta">
                    {e.note}
                    {e.actor && ` · ${e.actor.name}`} · {ago(e.created_at)}
                  </span>
                </span>
                <span className="ax-list__trailing">
                  <Status status={e.status} label={e.status_label} />
                </span>
              </li>
            ))}
          </ul>
        </Card>
      </div>
    </>
  );
}
