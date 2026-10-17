import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { AccountHero, ErrorAlert, RequestCard } from "@/components/account";
import { ActionForm } from "@/components/action-form";
import { SwitchLink } from "@/components/crafto";
import { ImageInput } from "@/components/image-input";
import { PageShell } from "@/components/page-shell";
import { api, requireMe } from "@/lib/api";
import type { ServiceRequest } from "@/lib/types";

export const metadata: Metadata = { title: "Mon espace" };

async function list(path: string, token: string) {
  const res = await api<ServiceRequest[]>(path, { token });
  return res.ok ? res.data : [];
}

type Props = { searchParams: Promise<{ erreur?: string; photo?: string }> };

const PHOTO_DONE: Record<string, string> = { ok: "Photo enregistrée.", retiree: "Photo retirée." };

export default async function DashboardPage({ searchParams }: Props) {
  const [{ me, token }, { erreur, photo }] = await Promise.all([
    requireMe("/espace"),
    searchParams,
  ]);
  if (me.is_staff) redirect("/console"); // L'équipe Jeflink travaille dans la console.
  const isPro = me.role === "pro";
  const [open, mine] = isPro
    ? await Promise.all([
        list("/api/requests/?scope=open", token),
        list("/api/requests/?scope=mine", token),
      ])
    : [[], await list("/api/requests/", token)];
  const verified = me.pro_profile?.is_verified ?? false;
  const note = me.pro_profile?.verification_note ?? ""; // motif d'un refus de vérification
  const hasId = (me.pro_profile?.documents ?? []).some(
    (d) => d.kind === "id" && d.status !== "rejected",
  );

  const logout = (
    <form action="/act/logout" method="post" className="mt-auto">
      <button type="submit" className="btn btn-link p-0 fs-15 fw-500 text-dark-gray">
        <i className="feather icon-feather-log-out me-5px" />
        Se déconnecter
      </button>
    </form>
  );

  return (
    <PageShell actions={false}>
      <AccountHero
        pill={isPro ? "Espace pro" : "Mon espace"}
        title={`Bonjour ${me.first_name || ""}.`}
        aside={
          <div className="jf-dashboard">
            {isPro ? (
              <>
                {!verified && (
                  <div
                    className="bg-white border-radius-20px p-30px sm-p-25px mb-40px d-flex flex-column flex-md-row align-items-md-center gap-3"
                    role="status"
                  >
                    <span className="status-pill status-open align-self-start align-self-md-center">
                      <i className="bi bi-hourglass-split" />{" "}
                      {note ? "À compléter" : "Vérification en cours"}
                    </span>
                    {note ? (
                      <p className="mb-0">
                        L&apos;équipe Jeflink n&apos;a pas encore pu vérifier votre profil&nbsp;:{" "}
                        <strong>{note.replace(/[.\s]+$/, "")}.</strong> Écrivez-nous depuis la page
                        Contact une fois corrigé.
                      </p>
                    ) : (
                      <p className="mb-0">
                        Vous voyez déjà les demandes de vos métiers. Vous pourrez envoyer des devis
                        dès que l&apos;équipe Jeflink aura vérifié votre profil.{" "}
                        {hasId ? (
                          "Votre pièce d'identité est entre ses mains."
                        ) : (
                          <a
                            href="/espace/profil#documents"
                            className="fw-500 text-decoration-line-bottom"
                          >
                            Envoyez votre pièce d&apos;identité.
                          </a>
                        )}
                      </p>
                    )}
                  </div>
                )}
                <h2 className="h5 alt-font fw-500 mb-20px">Demandes ouvertes dans vos métiers</h2>
                {open.length === 0 ? (
                  <p className="bg-white border-radius-20px p-30px mb-40px">
                    Aucune demande ouverte pour l&apos;instant. Revenez bientôt.
                  </p>
                ) : (
                  <div className="mb-40px">
                    {open.map((r) => (
                      <RequestCard key={r.id} req={r} viewer="pro" />
                    ))}
                  </div>
                )}
                <h2 className="h5 alt-font fw-500 mb-20px">Mes devis et missions</h2>
                {mine.length === 0 ? (
                  <p className="bg-white border-radius-20px p-30px">
                    Vos devis envoyés et vos missions apparaîtront ici.
                  </p>
                ) : (
                  mine.map((r) => <RequestCard key={r.id} req={r} viewer="pro" />)
                )}
              </>
            ) : (
              <>
                <h2 className="h5 alt-font fw-500 mb-20px">Mes demandes</h2>
                {mine.length === 0 ? (
                  <div className="bg-white border-radius-20px p-40px text-center">
                    <p className="fs-18 mb-25px">
                      Vous n&apos;avez pas encore de demande. Décrivez votre besoin : les pros de
                      votre quartier vous répondent.
                    </p>
                    <SwitchLink
                      href="/espace/demandes/nouvelle"
                      label="Faire une demande"
                      icon="icon-feather-edit"
                      className="btn-large btn-base-color btn-rounded btn-box-shadow"
                    />
                  </div>
                ) : (
                  mine.map((r) => <RequestCard key={r.id} req={r} viewer="client" />)
                )}
              </>
            )}
          </div>
        }
      >
        <ErrorAlert message={erreur} />
        {photo && PHOTO_DONE[photo] && (
          <div className="alert alert-success mb-25px" role="status">
            {PHOTO_DONE[photo]}
          </div>
        )}
        <div className="jf-profile-photo mb-25px">
          <ActionForm action="/act/photo" className="jf-profile-photo__form">
            <ImageInput
              id="ma-photo"
              name="photo"
              current={me.photo}
              maxSide={1000}
              previewClassName="jf-avatar"
              previewSize={80}
              className="visually-hidden"
              autoSubmit
            />
            {!me.photo && (
              <span className="jf-avatar jf-avatar--initials" aria-hidden="true">
                {initials(me.first_name, me.last_name)}
              </span>
            )}
            <span className="d-flex flex-column align-items-start">
              <label htmlFor="ma-photo" className="jf-link-button">
                <i className="feather icon-feather-camera me-5px" aria-hidden="true" />
                {me.photo ? "Changer ma photo" : "Ajouter ma photo"}
              </label>
              <span className="fs-13">
                {isPro
                  ? "Visible des clients sur votre profil."
                  : "Visible de l'équipe Jeflink seulement."}
              </span>
              <noscript>
                <button type="submit" className="btn btn-link p-0 fs-14">
                  Enregistrer la photo
                </button>
              </noscript>
            </span>
          </ActionForm>
          {me.photo && (
            <form action="/act/photo" method="post">
              <input type="hidden" name="remove" value="1" />
              <button type="submit" className="jf-link-button">
                Retirer ma photo
              </button>
            </form>
          )}
        </div>
        <p className="mb-25px">
          {isPro
            ? me.pro_profile?.headline ||
              "Retrouvez ici les demandes de vos métiers et vos missions."
            : "Suivez vos demandes, comparez les devis reçus et notez vos pros."}
        </p>
        {!isPro && (
          <SwitchLink
            href="/espace/demandes/nouvelle"
            label="Nouvelle demande"
            icon="icon-feather-plus"
            className="btn-large btn-base-color btn-rounded btn-box-shadow mb-30px"
          />
        )}
        <a
          href="/espace/profil"
          className="d-inline-block fw-500 text-decoration-line-bottom mb-20px"
        >
          <i className="feather icon-feather-user me-5px" aria-hidden="true" />
          {me.role === "pro" ? "Mon profil et mes quartiers" : "Mon profil et mes adresses"}
        </a>
        <ul className="list-unstyled fs-15 mb-30px">
          <li>
            <i className="feather icon-feather-mail me-10px" />
            {me.email}
          </li>
          {me.phone && (
            <li>
              <i className="feather icon-feather-phone me-10px" />
              {me.phone}
            </li>
          )}
        </ul>
        {logout}
      </AccountHero>
    </PageShell>
  );
}

function initials(first: string, last: string): string {
  return `${first.charAt(0)}${last.charAt(0)}`.toUpperCase() || "J";
}
