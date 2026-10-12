import type { Metadata } from "next";

import { AccountHero, ErrorAlert } from "@/components/account";
import { ActionForm } from "@/components/action-form";
import { SwitchSubmit } from "@/components/crafto";
import { PageShell } from "@/components/page-shell";
import { getTrades, getZones } from "@/lib/api";

export const metadata: Metadata = { title: "Créer un compte" };

const LABELS = {
  email: "Email",
  password: "Mot de passe",
  first_name: "Prénom",
  last_name: "Nom",
  phone: "Téléphone",
  trades: "Métiers",
  zones: "Quartiers",
  headline: "Accroche",
};

export default async function SignupPage({
  searchParams,
}: {
  searchParams: Promise<{ role?: string; suite?: string; erreur?: string }>;
}) {
  const { role: roleParam, suite = "/espace", erreur } = await searchParams;
  const pro = roleParam === "pro";
  const [trades, zones] = pro ? await Promise.all([getTrades(), getZones()]) : [[], []];

  return (
    <PageShell actions={false}>
      <AccountHero
        pill={pro ? "Espace pro" : "Créer un compte"}
        title={pro ? "Rejoignez les pros Jeflink." : "Votre premier pro est à deux minutes."}
        aside={
          <div className="bg-white border-radius-20px p-12 sm-p-7 h-100">
            <div
              className="d-flex flex-wrap gap-2 mb-30px"
              role="tablist"
              aria-label="Type de compte"
            >
              <a
                href="/inscription"
                role="tab"
                aria-selected={!pro}
                className={`btn btn-small btn-rounded ${pro ? "btn-transparent-dark-gray" : "btn-dark-gray"}`}
              >
                Je cherche un pro
              </a>
              <a
                href="/inscription?role=pro"
                role="tab"
                aria-selected={pro}
                className={`btn btn-small btn-rounded ${pro ? "btn-dark-gray" : "btn-transparent-dark-gray"}`}
              >
                Je suis un pro
              </a>
            </div>
            <ActionForm action="/act/register" className="jf-form" labels={LABELS}>
              <ErrorAlert message={erreur} />
              <input type="hidden" name="role" value={pro ? "pro" : "client"} />
              <input type="hidden" name="suite" value={suite} />
              <div className="row">
                <div className="col-md-6 mb-20px">
                  <label htmlFor="first_name">Prénom</label>
                  <input
                    id="first_name"
                    className="form-control"
                    name="first_name"
                    autoComplete="given-name"
                    required
                  />
                </div>
                <div className="col-md-6 mb-20px">
                  <label htmlFor="last_name">Nom</label>
                  <input
                    id="last_name"
                    className="form-control"
                    name="last_name"
                    autoComplete="family-name"
                  />
                </div>
                <div className="col-md-6 mb-20px">
                  <label htmlFor="email">Email</label>
                  <input
                    id="email"
                    className="form-control"
                    type="email"
                    name="email"
                    autoComplete="email"
                    required
                  />
                </div>
                <div className="col-md-6 mb-20px">
                  <label htmlFor="phone">Téléphone {pro ? "" : "(facultatif)"}</label>
                  <input
                    id="phone"
                    className="form-control"
                    type="tel"
                    name="phone"
                    placeholder="77 123 45 67"
                    autoComplete="tel-national"
                    inputMode="tel"
                    required={pro}
                  />
                  <div className="hint">Partagé seulement après réservation.</div>
                </div>
                <div className="col-12 mb-20px">
                  <label htmlFor="password">Mot de passe</label>
                  <input
                    id="password"
                    className="form-control"
                    type="password"
                    name="password"
                    autoComplete="new-password"
                    minLength={8}
                    required
                  />
                  <div className="hint">8 caractères au moins, pas trop courant.</div>
                </div>
              </div>
              {pro && (
                <>
                  <div className="mb-20px">
                    <label htmlFor="headline">Accroche</label>
                    <input
                      id="headline"
                      className="form-control"
                      name="headline"
                      maxLength={120}
                      placeholder="Ex. : Plombier à Ouakam depuis 10 ans"
                    />
                  </div>
                  <fieldset className="mb-20px border-0 p-0">
                    <legend className="fs-14 fw-500 text-dark-gray mb-10px">Vos métiers</legend>
                    <div className="jf-checks">
                      {trades.map((t) => (
                        <label key={t.slug}>
                          <input type="checkbox" name="trades" value={t.slug} />
                          <span>
                            <i className={`bi ${t.icon} text-base-color me-5px`} />
                            {t.name}
                          </span>
                        </label>
                      ))}
                    </div>
                  </fieldset>
                  <fieldset className="mb-30px border-0 p-0">
                    <legend className="fs-14 fw-500 text-dark-gray mb-5px">Vos quartiers</legend>
                    <div className="hint mb-10px mt-0">
                      Aucun coché : vous voyez les demandes de toute la zone.
                    </div>
                    <div className="jf-checks">
                      {zones.map((z) => (
                        <label key={z.slug}>
                          <input type="checkbox" name="zones" value={z.slug} />
                          <span>{z.name}</span>
                        </label>
                      ))}
                    </div>
                  </fieldset>
                </>
              )}
              <SwitchSubmit
                label="Créer mon compte"
                icon="icon-feather-user"
                className="btn-large btn-dark-gray btn-rounded btn-box-shadow"
              />
            </ActionForm>
          </div>
        }
      >
        <p className="mb-20px">
          {pro
            ? "Créez votre profil, choisissez vos métiers et vos quartiers. L'équipe Jeflink vérifie votre profil, puis vous pouvez envoyer des devis."
            : "Publiez votre besoin gratuitement, recevez jusqu'à trois devis de pros vérifiés et choisissez."}
        </p>
        <p className="mb-0">
          Déjà inscrit ?{" "}
          <a href="/connexion" className="text-decoration-line-bottom fw-500">
            Se connecter
          </a>
        </p>
      </AccountHero>
    </PageShell>
  );
}
