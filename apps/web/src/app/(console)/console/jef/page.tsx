import type { Metadata } from "next";
import Link from "next/link";

import { CardGrid } from "@/console/cards";
import { consoleGet, type Query } from "@/console/data";
import { Pager, Tabs } from "@/console/kit";
import { ago, plural } from "@/console/text";
import type { JefExchange, JefOverview, Page } from "@/console/types";
import { Kpi, PageHead } from "@/console/ui";

export const metadata: Metadata = { title: "Jef" };

const BASE = "/console/jef";
const NBSP = " ";

function percent(part: number, total: number): string {
  return total ? `${Math.round((100 * part) / total)}${NBSP}%` : "—";
}

export default async function JefPage({ searchParams }: { searchParams: Promise<Query> }) {
  const params = await searchParams;
  const data = await consoleGet<Page<JefExchange> & JefOverview>(BASE, "jef/", {
    published: params.publie === "oui" ? "1" : params.publie === "non" ? "0" : undefined,
    mode: params.mode === "ai" || params.mode === "guide" ? params.mode : undefined,
    page: params.page,
  });
  const { status, stats } = data;

  return (
    <>
      <PageHead
        title="Jef"
        subtitle={`L'assistant qui aide le client à décrire son souci${NBSP}: deux ou trois questions, puis une demande claire et une fiche pour le pro.`}
      />

      <div className="ax-dash-grid mb-6">
        <Kpi
          label="Mode"
          icon="bi-stars"
          dark
          value={!status.enabled ? "En pause" : status.ai ? "IA" : "Guidé"}
          foot={
            !status.enabled
              ? "Réactivable dans Réglages"
              : !status.ai
                ? "Pas de clé d'API : questions fixes par métier"
                : stats.sessions > 0 && stats.ai === 0
                  ? "Clé présente mais aucune réponse de l'IA : vérifiez le crédit du compte Anthropic"
                  : `Claude (${status.model}), repli sur les questions guidées`
          }
        />
        <Kpi
          label="Échanges, 30 jours"
          icon="bi-chat-dots"
          value={String(stats.sessions)}
          foot={`${percent(stats.ai, stats.sessions)} avec l'IA · ${status.daily_limit} par client et par jour au plus`}
        />
        <Kpi
          label="Fiches prêtes"
          icon="bi-card-checklist"
          value={String(stats.briefs)}
          foot={`${percent(stats.briefs, stats.sessions)} des échanges vont jusqu'à la fiche`}
        />
        <Kpi
          label="Demandes publiées avec Jef"
          icon="bi-send-check"
          value={String(stats.published)}
          foot={`${percent(stats.published, stats.requests)} sur ${plural(stats.requests, "demande publiée", "demandes publiées")} en 30 jours`}
        />
      </div>

      <Tabs
        base={BASE}
        params={params}
        name="publie"
        label="Échanges"
        tabs={[
          { value: "", label: "Tous" },
          { value: "oui", label: "Publiés" },
          { value: "non", label: "Sans demande" },
        ]}
      />
      <CardGrid empty="Aucun échange avec Jef pour l'instant.">
        {data.results.map((x) => (
          <article key={x.id} className="ax-card jf-item" aria-label={`Échange ${x.id}`}>
            <div className="jf-item__head">
              <div className="jf-item__titles">
                <span className="ax-card__eyebrow">
                  {x.trade || "Métier à préciser"} · {ago(x.created_at)}
                </span>
                <h2 className="jf-item__title">{x.client?.name ?? "Client supprimé"}</h2>
              </div>
              <div className="jf-item__aside">
                <span
                  className={`jf-status ${x.mode === "ai" ? "jf-status--done" : "jf-status--cancelled"}`}
                >
                  {x.mode === "ai" ? "IA" : "Guidé"}
                </span>
              </div>
            </div>
            <div className="jf-item__body jf-stack">
              <blockquote className="jf-quote">
                «{NBSP}
                {x.text}
                {NBSP}»
              </blockquote>
              {x.questions.length > 0 && (
                <dl className="jf-qa">
                  {x.questions.map((q) => (
                    <div key={q.id}>
                      <dt>{q.question}</dt>
                      <dd>{x.answers[q.id] || <span className="jf-muted">Sans réponse</span>}</dd>
                    </div>
                  ))}
                </dl>
              )}
              {x.brief ? (
                <div className="jf-mini">
                  <span className="jf-strong">
                    {x.brief.urgent && <span className="jf-status jf-status--open">Urgent</span>}{" "}
                    {x.brief.title}
                  </span>
                  {x.brief.pro_summary && <span className="jf-sub">{x.brief.pro_summary}</span>}
                </div>
              ) : (
                <p className="jf-muted">Le client n&apos;est pas allé jusqu&apos;à la fiche.</p>
              )}
            </div>
            <div className="jf-item__foot">
              {x.request ? (
                <Link href={`/console/demandes/${x.request.id}`} className="jf-link">
                  Demande #{x.request.id} {x.request.title}
                </Link>
              ) : (
                <span className="jf-muted">Pas de demande publiée</span>
              )}
            </div>
          </article>
        ))}
      </CardGrid>
      <Pager count={data.count} base={BASE} params={params} />
    </>
  );
}
