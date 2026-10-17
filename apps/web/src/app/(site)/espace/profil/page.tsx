import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { AccountHero, ErrorAlert } from "@/components/account";
import { ActionForm } from "@/components/action-form";
import { ImageInput } from "@/components/image-input";
import { SwitchSubmit } from "@/components/crafto";
import { PageShell } from "@/components/page-shell";
import { getZones, requireMe } from "@/lib/api";
import { formatDate } from "@/lib/format";
import type { ContactHours, ContactPref, Me, ProDocument, Zone } from "@/lib/types";

export const metadata: Metadata = { title: "Mon profil" };

const PREFS: { value: ContactPref; label: string }[] = [
  { value: "", label: "Appel ou WhatsApp" },
  { value: "call", label: "Appel" },
  { value: "whatsapp", label: "WhatsApp" },
];

const HOURS: { value: ContactHours; label: string }[] = [
  { value: "", label: "Toute la journée" },
  { value: "morning", label: "Le matin (8 h – 12 h)" },
  { value: "afternoon", label: "L'après-midi (12 h – 17 h)" },
  { value: "evening", label: "Le soir (17 h – 21 h)" },
];

const DONE: Record<string, string> = {
  profil: "Profil enregistré.",
  adresse: "Adresse enregistrée.",
  "adresse-retiree": "Adresse supprimée.",
  document: "Document envoyé : l'équipe Jeflink l'examine.",
  "document-retire": "Document retiré.",
};

const LABELS = {
  first_name: "Prénom",
  last_name: "Nom",
  phone: "Téléphone",
  headline: "Accroche",
  bio: "Présentation",
  years_experience: "Années d'expérience",
  zones: "Quartiers",
  label: "Nom de l'adresse",
  zone: "Quartier",
  landmark: "Repère",
};

const MAX_ADDRESSES = 5;

type Props = { searchParams: Promise<{ erreur?: string; ok?: string }> };

export default async function ProfilePage({ searchParams }: Props) {
  const [{ me }, { erreur, ok }, zones] = await Promise.all([
    requireMe("/espace/profil"),
    searchParams,
    getZones(),
  ]);
  if (me.is_staff) redirect("/console");
  const pro = me.pro_profile;

  return (
    <PageShell actions={false}>
      <AccountHero
        pill="Mon profil"
        title="Mon profil."
        aside={
          <div className="jf-dashboard">
            <ErrorAlert message={erreur} />
            {ok && DONE[ok] && (
              <div className="alert alert-success mb-25px" role="status">
                {DONE[ok]}
              </div>
            )}
            <section className="bg-white border-radius-20px p-40px sm-p-25px mb-30px">
              <h2 className="h5 alt-font fw-500 mb-25px">Mes informations</h2>
              <ActionForm action="/act/profil" className="jf-form" labels={LABELS}>
                <div className="row">
                  <div className="col-md-6 mb-20px">
                    <label htmlFor="first_name">Prénom</label>
                    <input
                      id="first_name"
                      name="first_name"
                      className="form-control"
                      defaultValue={me.first_name}
                      maxLength={150}
                      autoComplete="given-name"
                      required
                    />
                  </div>
                  <div className="col-md-6 mb-20px">
                    <label htmlFor="last_name">Nom</label>
                    <input
                      id="last_name"
                      name="last_name"
                      className="form-control"
                      defaultValue={me.last_name}
                      maxLength={150}
                      autoComplete="family-name"
                    />
                  </div>
                  <div className="col-md-6 mb-20px">
                    <label htmlFor="phone">Téléphone</label>
                    <input
                      id="phone"
                      name="phone"
                      type="tel"
                      className="form-control"
                      defaultValue={me.phone}
                      placeholder="77 123 45 67"
                      autoComplete="tel"
                    />
                    <div className="hint">
                      Partagé seulement avec {pro ? "le client" : "le pro"} d&apos;une mission
                      réservée, et avec le support Jeflink.
                    </div>
                  </div>
                  <div className="col-md-6 mb-20px">
                    <label htmlFor="contact_hours">Quand vous joindre</label>
                    <select
                      id="contact_hours"
                      name="contact_hours"
                      className="form-control"
                      defaultValue={me.contact_hours}
                    >
                      {HOURS.map((h) => (
                        <option key={h.value} value={h.value}>
                          {h.label}
                        </option>
                      ))}
                    </select>
                  </div>
                  <fieldset className="col-12 mb-20px border-0 p-0 px-3">
                    <legend className="fs-14 fw-500 text-dark-gray mb-10px">
                      Comment vous joindre
                    </legend>
                    <div className="jf-checks">
                      {PREFS.map((p) => (
                        <label key={p.value}>
                          <input
                            type="radio"
                            name="contact_pref"
                            value={p.value}
                            defaultChecked={me.contact_pref === p.value}
                          />
                          <span>{p.label}</span>
                        </label>
                      ))}
                    </div>
                  </fieldset>
                  {pro && <ProFields pro={pro} zones={zones} />}
                </div>
                <SwitchSubmit
                  label="Enregistrer"
                  icon="icon-feather-check"
                  className="btn-large btn-base-color btn-rounded btn-box-shadow"
                />
              </ActionForm>
            </section>

            {pro && <Documents documents={pro.documents} />}

            {!pro && (
              <section
                id="adresses"
                className="bg-white border-radius-20px p-40px sm-p-25px mb-30px"
                aria-labelledby="adresses-titre"
              >
                <h2 id="adresses-titre" className="h5 alt-font fw-500 mb-10px">
                  Mes adresses
                </h2>
                <p className="mb-25px">
                  Choisies en un geste quand vous faites une demande. Un quartier et un repère
                  suffisent.
                </p>
                {me.addresses.length > 0 && (
                  <ul className="list-unstyled mb-30px">
                    {me.addresses.map((a) => (
                      <li
                        key={a.id}
                        className="d-flex flex-wrap align-items-center justify-content-between gap-2 border-bottom border-color-extra-medium-gray py-15px"
                      >
                        <span>
                          <span className="d-block fw-500 text-dark-gray">
                            <i
                              className="feather icon-feather-map-pin text-base-color me-5px"
                              aria-hidden="true"
                            />
                            {a.label} · {a.zone_name}
                          </span>
                          {a.landmark && <span className="d-block fs-15">{a.landmark}</span>}
                        </span>
                        <form action={`/act/adresses/${a.id}`} method="post">
                          <button
                            type="submit"
                            className="jf-link-button"
                            aria-label={`Supprimer l'adresse ${a.label}`}
                          >
                            Supprimer
                          </button>
                        </form>
                      </li>
                    ))}
                  </ul>
                )}
                {me.addresses.length < MAX_ADDRESSES ? (
                  <ActionForm action="/act/adresses" className="jf-form" labels={LABELS}>
                    <div className="row">
                      <div className="col-md-5 mb-20px">
                        <label htmlFor="label">Nom de l&apos;adresse</label>
                        <input
                          id="label"
                          name="label"
                          className="form-control"
                          maxLength={40}
                          placeholder="Maison, Bureau…"
                          required
                        />
                      </div>
                      <div className="col-md-7 mb-20px">
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
                        <label htmlFor="landmark">Repère</label>
                        <input
                          id="landmark"
                          name="landmark"
                          className="form-control"
                          maxLength={160}
                          placeholder="Ex.&nbsp;: derrière la pharmacie, portail bleu, 2e étage"
                        />
                      </div>
                    </div>
                    <SwitchSubmit
                      label="Ajouter l'adresse"
                      icon="icon-feather-plus"
                      className="btn-medium btn-dark-gray btn-rounded"
                    />
                  </ActionForm>
                ) : (
                  <p className="mb-0 fs-15">
                    {MAX_ADDRESSES} adresses au plus&nbsp;: supprimez-en une pour en ajouter une
                    autre.
                  </p>
                )}
              </section>
            )}
          </div>
        }
      >
        <p className="mb-25px">
          {pro
            ? "Ce que les clients voient de vous, et comment l'équipe et vos clients vous joignent."
            : "Vos coordonnées et vos adresses : vos prochaines demandes vont plus vite."}
        </p>
        <a href="/espace" className="fw-500 text-decoration-line-bottom">
          <i className="feather icon-feather-arrow-left me-5px" aria-hidden="true" />
          Retour à mon espace
        </a>
      </AccountHero>
    </PageShell>
  );
}

const DOC_STATUS = {
  pending: "status-open",
  accepted: "status-done",
  rejected: "status-cancelled",
};

const DOC_KINDS = [
  { value: "id", label: "Pièce d'identité (CNI ou passeport)" },
  { value: "certificate", label: "Diplôme ou attestation" },
  { value: "other", label: "Autre justificatif" },
];

/** Justificatifs du pro : privés, vus par l'équipe Jeflink seulement. */
function Documents({ documents }: { documents: ProDocument[] }) {
  const hasId = documents.some((d) => d.kind === "id" && d.status !== "rejected");
  return (
    <section
      id="documents"
      className="bg-white border-radius-20px p-40px sm-p-25px mb-30px"
      aria-labelledby="documents-titre"
    >
      <h2 id="documents-titre" className="h5 alt-font fw-500 mb-10px">
        Mes documents
      </h2>
      <p className="mb-25px">
        Votre pièce d&apos;identité est obligatoire pour être vérifié et envoyer des devis. Vos
        diplômes et attestations rassurent les clients. Seule l&apos;équipe Jeflink les voit.
      </p>
      {documents.length > 0 && (
        <ul className="list-unstyled mb-30px">
          {documents.map((d) => (
            <li
              key={d.id}
              className="d-flex flex-wrap align-items-center justify-content-between gap-2 border-bottom border-color-extra-medium-gray py-15px"
            >
              <span>
                <span className="d-flex flex-wrap align-items-center gap-2 fw-500 text-dark-gray">
                  {d.kind_label}
                  <span className={`status-pill ${DOC_STATUS[d.status]}`}>{d.status_label}</span>
                </span>
                <span className="d-block fs-14">
                  Envoyé le {formatDate(d.created_at)}
                  {d.content_type === "application/pdf" ? " · PDF" : " · photo"}
                </span>
                {d.note && (
                  <span className="d-block fs-15 text-dark-gray">
                    Motif du refus&nbsp;: {d.note}
                  </span>
                )}
              </span>
              <span className="d-flex gap-3">
                <a
                  href={`/documents/${d.id}`}
                  className="jf-link-button"
                  target="_blank"
                  rel="noopener"
                >
                  Ouvrir
                </a>
                {d.status !== "accepted" && (
                  <form action={`/act/documents/${d.id}`} method="post">
                    <button
                      type="submit"
                      className="jf-link-button"
                      aria-label={`Retirer ${d.kind_label.toLowerCase()}`}
                    >
                      Retirer
                    </button>
                  </form>
                )}
              </span>
            </li>
          ))}
        </ul>
      )}
      <ActionForm
        action="/act/documents"
        className="jf-form"
        labels={{ kind: "Type", file: "Fichier" }}
      >
        <div className="row">
          <div className="col-md-6 mb-20px">
            <label htmlFor="kind">Type de document</label>
            <select
              id="kind"
              name="kind"
              className="form-control"
              defaultValue={hasId ? "certificate" : "id"}
            >
              {DOC_KINDS.map((k) => (
                <option key={k.value} value={k.value}>
                  {k.label}
                </option>
              ))}
            </select>
          </div>
          <div className="col-md-6 mb-20px">
            <label htmlFor="file">Photo ou PDF</label>
            <ImageInput
              id="file"
              name="file"
              accept="image/jpeg,image/png,image/webp,application/pdf"
              maxSide={2000}
              className="form-control"
              aria-describedby="file-aide"
              required
            />
            <div className="hint" id="file-aide">
              Photo nette, à plat, bien éclairée&nbsp;; 8&nbsp;Mo au plus.
            </div>
          </div>
        </div>
        <SwitchSubmit
          label="Envoyer le document"
          icon="icon-feather-upload"
          className="btn-medium btn-dark-gray btn-rounded"
        />
      </ActionForm>
    </section>
  );
}

function ProFields({ pro, zones }: { pro: NonNullable<Me["pro_profile"]>; zones: Zone[] }) {
  return (
    <>
      <div className="col-12 mb-20px">
        <label htmlFor="headline">Accroche</label>
        <input
          id="headline"
          name="headline"
          className="form-control"
          defaultValue={pro.headline}
          maxLength={120}
          placeholder="Ex.&nbsp;: Plombier à Ouakam, dépannage le jour même"
        />
        <div className="hint">Une phrase, sous votre nom sur vos devis et votre profil.</div>
      </div>
      <div className="col-md-9 mb-20px">
        <label htmlFor="bio">Présentation</label>
        <textarea
          id="bio"
          name="bio"
          className="form-control"
          rows={4}
          maxLength={1500}
          defaultValue={pro.bio}
          placeholder="Votre parcours, ce que vous faites le mieux, votre matériel…"
        />
      </div>
      <div className="col-md-3 mb-20px">
        <label htmlFor="years_experience">Années d&apos;expérience</label>
        <input
          id="years_experience"
          name="years_experience"
          type="number"
          min={0}
          max={60}
          className="form-control"
          defaultValue={pro.years_experience}
        />
      </div>
      <fieldset className="col-12 mb-25px border-0 p-0 px-3">
        <legend className="fs-14 fw-500 text-dark-gray mb-10px">
          Quartiers où vous intervenez
        </legend>
        <input type="hidden" name="zones_sent" value="1" />
        <div className="jf-checks">
          {zones.map((z) => (
            <label key={z.slug}>
              <input
                type="checkbox"
                name="zones"
                value={z.slug}
                defaultChecked={pro.zones.includes(z.slug)}
              />
              <span>{z.name}</span>
            </label>
          ))}
        </div>
        <div className="hint">
          Vous ne voyez que les demandes de ces quartiers&nbsp;; aucun coché, tous les quartiers.
        </div>
      </fieldset>
    </>
  );
}
