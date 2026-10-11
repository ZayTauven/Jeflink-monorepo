import type { Metadata } from "next";

import { AccountHero, ErrorAlert } from "@/components/account";
import { ActionForm } from "@/components/action-form";
import { SwitchSubmit } from "@/components/crafto";
import { PageShell } from "@/components/page-shell";

export const metadata: Metadata = { title: "Se connecter" };

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ suite?: string; erreur?: string }>;
}) {
  const { suite = "/espace", erreur } = await searchParams;
  const signup = `/inscription${suite !== "/espace" ? `?suite=${encodeURIComponent(suite)}` : ""}`;

  return (
    <PageShell>
      <AccountHero
        pill="Mon espace"
        title="Bon retour sur Jeflink."
        aside={
          <div className="bg-white border-radius-20px p-12 sm-p-7 h-100">
            <ActionForm
              action="/act/login"
              className="jf-form"
              labels={{ email: "Email", password: "Mot de passe" }}
            >
              <ErrorAlert message={erreur} />
              <input type="hidden" name="suite" value={suite} />
              <div className="mb-20px">
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
              <div className="mb-30px">
                <label htmlFor="password">Mot de passe</label>
                <input
                  id="password"
                  className="form-control"
                  type="password"
                  name="password"
                  autoComplete="current-password"
                  required
                />
              </div>
              <SwitchSubmit
                label="Se connecter"
                icon="icon-feather-log-in"
                className="btn-large btn-dark-gray btn-rounded btn-box-shadow"
              />
            </ActionForm>
            <p className="mt-30px mb-0 fs-15 opacity-7">
              Comptes de démonstration (client, pro, admin) : voir « Démo » dans le README du
              projet.
            </p>
          </div>
        }
      >
        <p className="mb-20px">
          Suivez vos demandes, comparez les devis et notez vos pros. Pros : retrouvez les demandes
          de vos métiers.
        </p>
        <p className="mb-20px">
          Pas encore de compte ?{" "}
          <a href={signup} className="text-decoration-line-bottom fw-500">
            Créer un compte
          </a>
        </p>
        <p className="mt-auto mb-0 fs-14 opacity-7">
          <i className="feather icon-feather-phone me-5px" />
          Connexion rapide par SMS : bientôt dans l&apos;application mobile.
        </p>
      </AccountHero>
    </PageShell>
  );
}
