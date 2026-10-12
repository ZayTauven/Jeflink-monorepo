import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { AccountHero, RequestCard } from "@/components/account";
import { SwitchLink } from "@/components/crafto";
import { PageShell } from "@/components/page-shell";
import { api, requireMe } from "@/lib/api";
import type { ServiceRequest } from "@/lib/types";

export const metadata: Metadata = { title: "Mon espace" };

async function list(path: string, token: string) {
  const res = await api<ServiceRequest[]>(path, { token });
  return res.ok ? res.data : [];
}

export default async function DashboardPage() {
  const { me, token } = await requireMe("/espace");
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
                        dès que l&apos;équipe Jeflink aura vérifié votre profil
                        <span className="opacity-7"> (démo : console, rubrique Pros)</span>.
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
