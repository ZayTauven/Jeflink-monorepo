import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { Fragment } from "react";

import { AccountHero, ErrorAlert, StatusPill } from "@/components/account";
import { ActionForm } from "@/components/action-form";
import { SwitchSubmit } from "@/components/crafto";
import { PageShell } from "@/components/page-shell";
import { getRequest, requireMe } from "@/lib/api";
import { formatDate, formatRating, formatXOF } from "@/lib/format";
import type { Dispute, ServiceRequest } from "@/lib/types";

export const metadata: Metadata = { title: "Demande" };

type Props = {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ erreur?: string }>;
};

export default async function RequestPage({ params, searchParams }: Props) {
  const [{ id }, { erreur }] = await Promise.all([params, searchParams]);
  const { me, token } = await requireMe(`/espace/demandes/${id}`);
  const req = await getRequest(id, token);
  if (!req) notFound();

  const isClient = me.id === req.client.id;
  const act = (action: string) => `/act/requests/${req.id}/${action}`;
  const can = (a: ServiceRequest["actions"][number]) => req.actions.includes(a);

  return (
    <PageShell actions={false}>
      <AccountHero
        pill={`Demande n° ${req.id}`}
        title={req.title}
        aside={
          <div>
            <ErrorAlert message={erreur} />
            <Quotes req={req} isClient={isClient} act={act} canAccept={can("accept")} />
            {can("quote") && <QuoteForm act={act} />}
            {req.status === "open" && !isClient && !can("quote") && req.quotes.length === 0 && (
              <p className="bg-white border-radius-20px p-30px">
                {me.pro_profile?.is_verified
                  ? "Cette demande a déjà reçu le nombre maximal de devis."
                  : "Votre profil doit être vérifié par l'équipe Jeflink avant d'envoyer un devis."}
              </p>
            )}
            {can("review") && <ReviewForm act={act} proName={req.pro?.name ?? "le pro"} />}
            {req.review && (
              <div className="bg-white border-radius-20px p-30px mb-30px">
                <h2 className="h5 alt-font fw-500 mb-10px">Avis du client</h2>
                <div
                  className="jf-stars fs-20 mb-10px"
                  role="img"
                  aria-label={`Note : ${req.review.rating} sur 5`}
                >
                  {"★".repeat(req.review.rating)}
                  <span className="opacity-3">{"★".repeat(5 - req.review.rating)}</span>
                </div>
                {req.review.comment && <p className="mb-0">« {req.review.comment} »</p>}
              </div>
            )}
            {req.dispute && <DisputeCard dispute={req.dispute} />}
            {can("report") && <ReportForm act={act} isClient={isClient} />}
            <div className="bg-white border-radius-20px p-30px">
              <h2 className="h5 alt-font fw-500 mb-20px">Historique</h2>
              <ol className="jf-timeline">
                {req.events.map((e, i) => (
                  <li key={i}>
                    <span className="fw-500 text-dark-gray">{e.note}</span>
                    <span className="d-block fs-14 opacity-7">
                      {formatDate(e.created_at, true)}
                    </span>
                  </li>
                ))}
              </ol>
            </div>
          </div>
        }
      >
        <div className="d-flex flex-wrap align-items-center gap-2 mb-20px">
          <StatusPill status={req.status} label={req.status_label} />
          {req.is_urgent && <span className="status-pill status-open">Urgent</span>}
        </div>
        <ul className="list-unstyled fs-16 mb-20px">
          <li className="mb-5px">
            <i className={`bi ${req.trade.icon} text-base-color me-10px`} />
            {req.trade.name}
          </li>
          <li className="mb-5px">
            <i className="feather icon-feather-map-pin text-base-color me-10px" />
            {req.zone.name}
            {req.landmark && ` · ${req.landmark}`}
          </li>
          {req.preferred_date && (
            <li className="mb-5px">
              <i className="feather icon-feather-calendar text-base-color me-10px" />
              Souhaitée le {formatDate(req.preferred_date)}
            </li>
          )}
          {!isClient && (
            <li className="mb-5px">
              <i className="feather icon-feather-user text-base-color me-10px" />
              {req.client.name}
            </li>
          )}
        </ul>
        <p className="mb-25px">{req.description}</p>
        {req.pro && (
          <div className="border-top border-color-transparent-dark-light pt-20px mb-25px w-100">
            <span className="d-block fs-14 text-uppercase fw-500 opacity-7 mb-5px">
              {isClient ? "Votre pro" : "Mission"}
            </span>
            <span className="d-block alt-font fs-22 fw-500">
              {isClient ? req.pro.name : req.client.name}
            </span>
            {req.contact_phone && (
              <a href={`tel:${req.contact_phone}`} className="fw-500 text-decoration-line-bottom">
                <i className="feather icon-feather-phone me-5px" />
                {req.contact_phone}
              </a>
            )}
          </div>
        )}
        <div className="d-flex flex-wrap gap-3 mt-auto">
          {can("complete") && (
            <form action={act("complete")} method="post">
              <SwitchSubmit
                label="Marquer comme terminée"
                icon="icon-feather-check"
                className="btn-medium btn-dark-gray btn-rounded btn-box-shadow"
              />
            </form>
          )}
          {can("cancel") && (
            <form action={act("cancel")} method="post">
              <button type="submit" className="btn btn-link p-0 fs-15 fw-500 text-dark-gray">
                Annuler la demande
              </button>
            </form>
          )}
        </div>
        <a href="/espace" className="fs-15 fw-500 mt-25px">
          ← Retour à mon espace
        </a>
      </AccountHero>
    </PageShell>
  );
}

function Quotes({
  req,
  isClient,
  act,
  canAccept,
}: {
  req: ServiceRequest;
  isClient: boolean;
  act: (a: string) => string;
  canAccept: boolean;
}) {
  if (req.quotes.length === 0) {
    if (!isClient) return null;
    return (
      <div className="bg-white border-radius-20px p-30px mb-30px">
        <h2 className="h5 alt-font fw-500 mb-10px">Devis</h2>
        <p className="mb-0">
          {req.status === "open"
            ? "Aucun devis pour l'instant. Les pros vérifiés de ce métier voient votre demande dans leur espace : leurs devis arriveront ici."
            : "Aucun devis."}
        </p>
      </div>
    );
  }
  return (
    <div className="mb-30px">
      <h2 className="h5 alt-font fw-500 mb-20px">
        {isClient ? `Devis reçus (${req.quotes.length}/3)` : "Votre devis"}
      </h2>
      {req.quotes.map((q) => (
        <div
          key={q.id}
          className={`bg-white border-radius-20px p-30px sm-p-25px mb-20px${q.status === "accepted" ? " border border-2 border-color-base-color" : ""}`}
        >
          <div className="d-flex flex-wrap justify-content-between align-items-start gap-3">
            <div>
              <span className="alt-font fs-30 fw-600 ls-minus-1px d-block">
                {formatXOF(q.amount)}
              </span>
              <span className="fw-500 text-dark-gray">{q.pro.name}</span>
              {q.pro_headline && <span className="opacity-7"> · {q.pro_headline}</span>}
              <span className="d-block fs-14 opacity-7">
                {q.pro_rating.count > 0
                  ? `★ ${formatRating(q.pro_rating.average)} · ${q.pro_rating.count} avis`
                  : "Nouveau sur Jeflink"}
              </span>
            </div>
            <span className="status-pill status-cancelled">{q.status_label}</span>
          </div>
          {q.message && <p className="mt-15px mb-0">{q.message}</p>}
          {canAccept && q.status === "pending" && (
            <ActionForm action={act("accept")} className="mt-20px">
              <input type="hidden" name="quote_id" value={q.id} />
              <SwitchSubmit
                label="Choisir ce devis"
                icon="icon-feather-check"
                className="btn-medium btn-base-color btn-rounded btn-box-shadow"
              />
            </ActionForm>
          )}
        </div>
      ))}
    </div>
  );
}

function QuoteForm({ act }: { act: (a: string) => string }) {
  return (
    <div className="bg-white border-radius-20px p-30px mb-30px">
      <h2 className="h5 alt-font fw-500 mb-20px">Envoyer un devis</h2>
      <ActionForm
        action={act("quotes")}
        className="jf-form"
        labels={{ amount: "Montant", message: "Message" }}
      >
        <div className="mb-20px">
          <label htmlFor="amount">Montant (F CFA)</label>
          <input
            id="amount"
            name="amount"
            className="form-control"
            inputMode="numeric"
            pattern="[0-9 ]*"
            placeholder="15000"
            required
          />
          <div className="hint">Un montant entier, déplacement et pièces compris si possible.</div>
        </div>
        <div className="mb-25px">
          <label htmlFor="message">Ce que comprend le devis</label>
          <textarea
            id="message"
            name="message"
            rows={3}
            className="form-control"
            placeholder="Ex. : changement du siphon et des joints, pièces comprises."
          />
        </div>
        <SwitchSubmit
          label="Envoyer le devis"
          icon="icon-feather-send"
          className="btn-large btn-base-color btn-rounded btn-box-shadow"
        />
      </ActionForm>
    </div>
  );
}

// Mêmes valeurs que jobs.models.Dispute.Reason ; l'API refuse tout autre motif.
const CLIENT_REASONS: [string, string][] = [
  ["no_show", "Le pro n'est pas venu, ou très en retard"],
  ["quality", "Travail mal fait ou inachevé"],
  ["price", "Prix différent du devis"],
  ["damage", "Dégât chez moi"],
  ["behaviour", "Comportement"],
  ["other", "Autre"],
];
const PRO_REASONS: [string, string][] = [
  ["payment", "Paiement non reçu"],
  ["behaviour", "Comportement du client"],
  ["other", "Autre"],
];

const DISPUTE_PILL: Record<Dispute["status"], string> = {
  open: "status-open",
  investigating: "status-booked",
  resolved: "status-done",
  dismissed: "status-cancelled",
};

function DisputeCard({ dispute }: { dispute: Dispute }) {
  return (
    <div className="bg-white border-radius-20px p-30px mb-30px">
      <div className="d-flex flex-wrap justify-content-between align-items-center gap-2 mb-15px">
        <h2 className="h5 alt-font fw-500 mb-0">Problème signalé</h2>
        <span className={`status-pill ${DISPUTE_PILL[dispute.status]}`}>
          {dispute.status_label}
        </span>
      </div>
      <p className="mb-5px fw-500 text-dark-gray">{dispute.reason_label}</p>
      <p className="mb-15px">{dispute.description}</p>
      {dispute.resolution ? (
        <p className="mb-0">
          <span className="fw-500 text-dark-gray">Décision de l&apos;équipe Jeflink&nbsp;:</span>{" "}
          {dispute.resolution}
        </p>
      ) : (
        <p className="mb-0 fs-15 opacity-7">
          L&apos;équipe Jeflink examine le signalement et écrira sa décision ici.
        </p>
      )}
    </div>
  );
}

function ReportForm({ act, isClient }: { act: (a: string) => string; isClient: boolean }) {
  const reasons = isClient ? CLIENT_REASONS : PRO_REASONS;
  return (
    <details className="bg-white border-radius-20px p-30px mb-30px">
      <summary className="fw-500 text-dark-gray jf-summary">Signaler un problème</summary>
      <ActionForm
        action={act("report")}
        className="jf-form mt-20px"
        labels={{ reason: "Motif", description: "Ce qui s'est passé" }}
      >
        <div className="mb-20px">
          <label htmlFor="reason">Motif</label>
          <select id="reason" name="reason" className="form-control" required defaultValue="">
            <option value="" disabled>
              Choisir…
            </option>
            {reasons.map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </div>
        <div className="mb-25px">
          <label htmlFor="description">Ce qui s&apos;est passé</label>
          <textarea
            id="description"
            name="description"
            rows={3}
            className="form-control"
            required
          />
          <div className="hint">
            L&apos;équipe Jeflink examine chaque signalement. Sa décision s&apos;affichera sur cette
            page.
          </div>
        </div>
        <SwitchSubmit
          label="Envoyer le signalement"
          icon="icon-feather-alert-triangle"
          className="btn-medium btn-dark-gray btn-rounded btn-box-shadow"
        />
      </ActionForm>
    </details>
  );
}

function ReviewForm({ act, proName }: { act: (a: string) => string; proName: string }) {
  return (
    <div className="bg-white border-radius-20px p-30px mb-30px">
      <h2 className="h5 alt-font fw-500 mb-20px">
        Comment s&apos;est passée la mission avec {proName} ?
      </h2>
      <ActionForm
        action={act("review")}
        className="jf-form"
        labels={{ rating: "Note", comment: "Commentaire" }}
      >
        <fieldset className="border-0 p-0 mb-20px">
          <legend className="fs-14 fw-500 text-dark-gray mb-5px">Votre note</legend>
          <div className="jf-rating-input">
            {[5, 4, 3, 2, 1].map((n) => (
              <Fragment key={n}>
                <input
                  type="radio"
                  id={`rating-${n}`}
                  name="rating"
                  value={n}
                  aria-label={`${n} sur 5`}
                  required
                />
                <label htmlFor={`rating-${n}`} aria-hidden="true">
                  ★
                </label>
              </Fragment>
            ))}
          </div>
        </fieldset>
        <div className="mb-25px">
          <label htmlFor="comment">Un mot pour les prochains clients (facultatif)</label>
          <textarea id="comment" name="comment" rows={3} className="form-control" />
        </div>
        <SwitchSubmit
          label="Publier mon avis"
          icon="icon-feather-star"
          className="btn-large btn-dark-gray btn-rounded btn-box-shadow"
        />
      </ActionForm>
    </div>
  );
}
