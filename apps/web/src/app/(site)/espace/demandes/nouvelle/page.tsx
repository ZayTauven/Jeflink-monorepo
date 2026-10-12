import type { Metadata } from "next";

import { AccountHero, ErrorAlert } from "@/components/account";
import { ActionForm } from "@/components/action-form";
import { CampaignBanner } from "@/components/campaign-banner";
import { SwitchSubmit } from "@/components/crafto";
import { PageShell } from "@/components/page-shell";
import { getSite, getTrades, getZones, requireMe } from "@/lib/api";

export const metadata: Metadata = { title: "Nouvelle demande" };

const LABELS = {
  trade: "Métier",
  zone: "Quartier",
  title: "Titre",
  description: "Description",
  landmark: "Repère",
  preferred_date: "Date souhaitée",
};

export default async function NewRequestPage({
  searchParams,
}: {
  searchParams: Promise<{ metier?: string; erreur?: string }>;
}) {
  const { metier, erreur } = await searchParams;
  const here = `/espace/demandes/nouvelle${metier ? `?metier=${encodeURIComponent(metier)}` : ""}`;
  const { me } = await requireMe(here);
  const [trades, zones, site] = await Promise.all([getTrades(), getZones(), getSite()]);
  const today = new Date().toISOString().slice(0, 10);

  return (
    <PageShell actions={false}>
      <AccountHero
        pill="Nouvelle demande"
        title="Décrivez votre besoin."
        aside={
          <div className="bg-white border-radius-20px p-12 sm-p-7 h-100">
            {me.role === "pro" ? (
              <p className="fs-18 mb-0">
                Vous êtes connecté avec un compte pro. Pour publier une demande, utilisez un compte
                client.
              </p>
            ) : !site.accepting_requests ? (
              <div role="status">
                <span className="status-pill status-cancelled mb-20px d-inline-block">
                  Demandes en pause
                </span>
                <p className="fs-18 mb-15px">
                  {site.closed_message ||
                    "Jeflink ne prend pas de nouvelles demandes pour le moment."}
                </p>
                <p className="mb-25px">Les demandes déjà publiées continuent normalement.</p>
                <a href="/espace" className="fw-500 text-decoration-line-bottom">
                  Voir mes demandes
                </a>
              </div>
            ) : (
              <>
                <CampaignBanner placement="request" />
                <ActionForm action="/act/requests" className="jf-form" labels={LABELS}>
                  <ErrorAlert message={erreur} />
                  <div className="row">
                    <div className="col-md-6 mb-20px">
                      <label htmlFor="trade">Métier</label>
                      <select
                        id="trade"
                        name="trade"
                        className="form-control"
                        defaultValue={metier ?? ""}
                        required
                      >
                        <option value="" disabled>
                          Choisir…
                        </option>
                        {trades.map((t) => (
                          <option key={t.slug} value={t.slug}>
                            {t.name}
                          </option>
                        ))}
                      </select>
                    </div>
                    <div className="col-md-6 mb-20px">
                      <label htmlFor="zone">Quartier</label>
                      <select
                        id="zone"
                        name="zone"
                        className="form-control"
                        defaultValue=""
                        required
                      >
                        <option value="" disabled>
                          Choisir…
                        </option>
                        {zones.map((z) => (
                          <option key={z.slug} value={z.slug}>
                            {z.name}
                          </option>
                        ))}
                      </select>
                    </div>
                    <div className="col-12 mb-20px">
                      <label htmlFor="title">En une phrase</label>
                      <input
                        id="title"
                        name="title"
                        className="form-control"
                        maxLength={120}
                        placeholder="Ex. : Fuite sous l'évier de la cuisine"
                        required
                      />
                    </div>
                    <div className="col-12 mb-20px">
                      <label htmlFor="description">Ce qui se passe</label>
                      <textarea
                        id="description"
                        name="description"
                        className="form-control"
                        rows={4}
                        placeholder="Depuis quand, ce que vous avez remarqué, le matériel concerné…"
                        required
                      />
                    </div>
                    <div className="col-md-7 mb-20px">
                      <label htmlFor="landmark">Repère pour trouver la maison</label>
                      <input
                        id="landmark"
                        name="landmark"
                        className="form-control"
                        maxLength={160}
                        placeholder="Ex. : derrière la mosquée, portail vert"
                      />
                      <div className="hint">Visible des pros. Pas besoin du numéro de rue.</div>
                    </div>
                    <div className="col-md-5 mb-20px">
                      <label htmlFor="preferred_date">Date souhaitée</label>
                      <input
                        id="preferred_date"
                        name="preferred_date"
                        type="date"
                        min={today}
                        className="form-control"
                      />
                    </div>
                    <div className="col-12 mb-30px">
                      <div className="jf-checks">
                        <label>
                          <input type="checkbox" name="is_urgent" />
                          <span>C&apos;est urgent</span>
                        </label>
                      </div>
                    </div>
                  </div>
                  <SwitchSubmit
                    label="Publier la demande"
                    icon="icon-feather-send"
                    className="btn-large btn-base-color btn-rounded btn-box-shadow"
                  />
                </ActionForm>
              </>
            )}
          </div>
        }
      >
        <p className="mb-20px">
          Gratuit et sans engagement. Les pros vérifiés de votre quartier vous envoient jusqu&apos;à
          trois devis en F CFA, vous choisissez.
        </p>
        <p className="mb-0 fs-15 opacity-7">
          Votre numéro n&apos;est partagé qu&apos;avec le pro que vous aurez choisi.
        </p>
      </AccountHero>
    </PageShell>
  );
}
