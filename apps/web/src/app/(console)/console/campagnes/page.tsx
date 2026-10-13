import type { Metadata } from "next";

import { CardGrid } from "@/console/cards";
import { consoleGet, type Query } from "@/console/data";
import { CampaignForm } from "@/console/forms";
import { Flash } from "@/console/kit";
import { Modal } from "@/console/modal";
import { plural } from "@/console/text";
import type { CampaignAdmin } from "@/console/types";
import { PageHead } from "@/console/ui";
import { formatDate } from "@/lib/format";

export const metadata: Metadata = { title: "Campagnes" };

const BASE = "/console/campagnes";

export default async function CampaignsPage({ searchParams }: { searchParams: Promise<Query> }) {
  const params = await searchParams;
  const campaigns = await consoleGet<CampaignAdmin[]>(BASE, "campaigns/");
  const live = campaigns.filter((c) => c.is_live).length;

  return (
    <>
      <PageHead
        title="Campagnes"
        subtitle={`${plural(live, "campagne visible", "campagnes visibles")} sur le site en ce moment. Trois bandeaux au plus par emplacement ; au-delà, seuls les plus récents s'affichent.`}
        actions={
          <Modal
            trigger="Nouvelle campagne"
            triggerClassName="ax-btn ax-btn--primary"
            title="Nouvelle campagne"
            subtitle="Un bandeau sur le site, sur une période."
            size="lg"
          >
            <CampaignForm back={BASE} prefix="nouvelle" />
          </Modal>
        }
      />
      <Flash ok={params.ok} erreur={params.erreur} />
      <CardGrid empty="Aucune campagne pour l'instant.">
        {campaigns.map((c) => (
          <article key={c.id} className="ax-card jf-item" aria-label={c.title}>
            <div className="jf-item__head">
              <div className="jf-item__titles">
                <span className="ax-card__eyebrow">{c.placement_label}</span>
                <h2 className="jf-item__title">{c.title}</h2>
              </div>
              <div className="jf-item__aside">
                <span
                  className={`jf-status ${c.is_live ? "jf-status--done" : "jf-status--cancelled"}`}
                >
                  {c.is_live ? "En ligne" : c.is_active ? "Hors période" : "Désactivée"}
                </span>
              </div>
            </div>
            <div className="jf-item__body">
              {/* Aperçu du bandeau tel qu'il apparaît sur le site. */}
              <div className="jf-campaign-preview">
                <p>{c.message}</p>
                {c.coupon_code && <span className="jf-code">{c.coupon_code}</span>}
                {c.cta_label && <span className="jf-campaign-preview__cta">{c.cta_label} →</span>}
              </div>
            </div>
            <div className="jf-item__foot">
              <dl className="jf-item__stats">
                <div>
                  <dt>Période</dt>
                  <dd>
                    {c.starts_on
                      ? `${c.ends_on ? "" : "Depuis le "}${formatDate(c.starts_on)}`
                      : "Dès maintenant"}
                    {c.ends_on ? ` → ${formatDate(c.ends_on)}` : c.starts_on ? "" : ", sans fin"}
                  </dd>
                </div>
                {c.cta_url && (
                  <div>
                    <dt>Lien</dt>
                    <dd>{c.cta_url}</dd>
                  </div>
                )}
              </dl>
              <div className="jf-item__actions">
                <Modal trigger="Modifier" title="Modifier la campagne" subtitle={c.title} size="lg">
                  <CampaignForm campaign={c} back={BASE} prefix={`campagne-${c.id}`} />
                </Modal>
              </div>
            </div>
          </article>
        ))}
      </CardGrid>
    </>
  );
}
