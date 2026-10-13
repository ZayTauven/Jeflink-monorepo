import type { Metadata } from "next";

import { CardGrid } from "@/console/cards";
import { consoleGet, type Query } from "@/console/data";
import { Field } from "@/console/forms";
import { ActionButton, ActionForm, Avatar, Flash, ReasonAction } from "@/console/kit";
import { Modal } from "@/console/modal";
import { Submit } from "@/console/submit";
import { ago } from "@/console/text";
import type { Member, StaffRole } from "@/console/types";
import { Card, PageHead } from "@/console/ui";
import { requireStaff } from "@/lib/api";

export const metadata: Metadata = { title: "Équipe et rôles" };

const BASE = "/console/equipe";

const ROLES: { value: StaffRole; label: string; sees: string }[] = [
  { value: "super", label: "Super admin", sees: "Tout, y compris l'équipe et les réglages." },
  {
    value: "ops",
    label: "Opérations",
    sees: "Demandes, litiges, pros, clients, avis, messages, journal, catalogue.",
  },
  {
    value: "marketing",
    label: "Marketing",
    sees: "Tableau de bord, catalogue ; codes promo et campagnes à venir.",
  },
  { value: "finance", label: "Finance", sees: "Tableau de bord ; finances à venir." },
];

const ROLE_CLASS: Record<StaffRole, string> = {
  super: "jf-status--open",
  ops: "jf-status--booked",
  marketing: "jf-status--done",
  finance: "jf-status--cancelled",
};

export default async function TeamPage({ searchParams }: { searchParams: Promise<Query> }) {
  const params = await searchParams;
  const [{ me }, members] = await Promise.all([
    requireStaff(BASE),
    consoleGet<Member[]>(BASE, "team/"),
  ]);

  return (
    <>
      <PageHead
        title="Équipe et rôles"
        subtitle="Chaque membre voit les rubriques de son rôle. Retirer l'accès déconnecte la personne tout de suite."
        actions={
          <Modal
            trigger="Ajouter un membre"
            triggerClassName="ax-btn ax-btn--primary"
            title="Ajouter un membre"
            subtitle="Un mot de passe provisoire est créé : transmettez-le de vive voix."
          >
            <ActionForm
              endpoint="/api/console/team/"
              back={BASE}
              ok="Membre ajouté. Transmettez-lui son mot de passe provisoire de vive voix."
              className="jf-form"
            >
              <Field id="membre-first_name" label="Prénom">
                <input id="membre-first_name" name="first_name" className="ax-input" required />
              </Field>
              <Field id="membre-last_name" label="Nom">
                <input id="membre-last_name" name="last_name" className="ax-input" />
              </Field>
              <Field id="membre-email" label="Email" wide>
                <input id="membre-email" name="email" type="email" className="ax-input" required />
              </Field>
              <Field id="membre-role" label="Rôle">
                <select id="membre-role" name="role" className="ax-select" defaultValue="ops">
                  {ROLES.map((r) => (
                    <option key={r.value} value={r.value}>
                      {r.label}
                    </option>
                  ))}
                </select>
              </Field>
              <Field
                id="password"
                label="Mot de passe provisoire"
                hint="10 caractères au moins, pas un mot courant."
              >
                <input
                  id="password"
                  name="password"
                  type="password"
                  className="ax-input"
                  minLength={10}
                  required
                  autoComplete="new-password"
                />
              </Field>
              <div className="jf-form__wide">
                <Submit>Ajouter à l&apos;équipe</Submit>
              </div>
            </ActionForm>
          </Modal>
        }
      />
      <Flash ok={params.ok} erreur={params.erreur} />

      <div className="jf-stack">
        <CardGrid empty="Personne dans l'équipe.">
          {members.map((m) => {
            const self = m.id === me.id;
            return (
              <article key={m.id} className="ax-card jf-item" aria-label={m.name}>
                <div className="jf-item__head">
                  <Avatar name={m.name} size={48} />
                  <div className="jf-item__titles">
                    <span className="ax-card__eyebrow">{m.email}</span>
                    <h2 className="jf-item__title">
                      {m.name}
                      {self && <span className="jf-sub">C&apos;est vous</span>}
                    </h2>
                  </div>
                  <div className="jf-item__aside jf-inline jf-inline--end">
                    {!m.is_active && (
                      <span className="jf-status jf-status--cancelled">Accès retiré</span>
                    )}
                    <span className={`jf-status ${ROLE_CLASS[m.role]}`}>{m.role_label}</span>
                  </div>
                </div>
                <div className="jf-item__foot">
                  <dl className="jf-item__stats">
                    <div>
                      <dt>Dernière connexion</dt>
                      <dd>{m.last_login ? ago(m.last_login) : "Jamais"}</dd>
                    </div>
                    <div>
                      <dt>Membre depuis</dt>
                      <dd>{ago(m.date_joined)}</dd>
                    </div>
                  </dl>
                  {!self && !m.is_superuser && (
                    <div className="jf-item__actions">
                      {m.is_active && (
                        <ActionForm
                          endpoint={`/api/console/team/${m.id}/role/`}
                          back={BASE}
                          ok="Rôle modifié."
                          className="jf-role-form"
                        >
                          <label className="ax-visually-hidden" htmlFor={`role-${m.id}`}>
                            Rôle de {m.name}
                          </label>
                          <select
                            id={`role-${m.id}`}
                            name="role"
                            className="ax-select ax-select--sm"
                            defaultValue={m.role}
                          >
                            {ROLES.map((r) => (
                              <option key={r.value} value={r.value}>
                                {r.label}
                              </option>
                            ))}
                          </select>
                          <Submit className="ax-btn ax-btn--secondary ax-btn--sm">Changer</Submit>
                        </ActionForm>
                      )}
                      {m.is_active ? (
                        <ReasonAction
                          endpoint={`/api/console/team/${m.id}/deactivate/`}
                          back={BASE}
                          ok="Accès retiré : la personne est déconnectée."
                          label="Retirer l'accès…"
                          subject={m.name}
                          confirm="Retirer l'accès"
                          field="note"
                          placeholder={`Pour le journal, ex. : fin de contrat.`}
                        />
                      ) : (
                        <ActionButton
                          endpoint={`/api/console/team/${m.id}/reactivate/`}
                          back={BASE}
                          ok="Accès rétabli."
                          label="Rétablir l'accès"
                          variant="ax-btn ax-btn--secondary ax-btn--sm"
                        />
                      )}
                    </div>
                  )}
                </div>
              </article>
            );
          })}
        </CardGrid>

        <Card title="Les rôles" eyebrow="Qui voit quoi">
          <dl className="jf-facts">
            {ROLES.map((r) => (
              <div key={r.value}>
                <dt>{r.label}</dt>
                <dd>{r.sees}</dd>
              </div>
            ))}
          </dl>
        </Card>
      </div>
    </>
  );
}
