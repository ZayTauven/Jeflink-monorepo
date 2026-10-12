import type { Metadata } from "next";

import { consoleGet, type Query } from "@/console/data";
import { Check, Field } from "@/console/forms";
import { ActionForm, Flash } from "@/console/kit";
import { Submit } from "@/console/submit";
import type { PlatformSettings } from "@/console/types";
import { Card, PageHead } from "@/console/ui";
import { formatDate } from "@/lib/format";

export const metadata: Metadata = { title: "Réglages" };

const BASE = "/console/reglages";
const NBSP = " ";

export default async function SettingsPage({ searchParams }: { searchParams: Promise<Query> }) {
  const params = await searchParams;
  const s = await consoleGet<PlatformSettings>(BASE, "settings/");

  return (
    <>
      <PageHead
        title="Réglages"
        subtitle={
          s.updated_by
            ? `Dernière modification le ${formatDate(s.updated_at, true)} par ${s.updated_by.name}.`
            : "Règles de fonctionnement de la plateforme. Chaque modification est inscrite au journal."
        }
      />
      <Flash ok={params.ok} erreur={params.erreur} />
      <ActionForm endpoint="/api/console/settings/" back={BASE} ok="Réglages enregistrés.">
        <div className="ax-dash-grid">
          <Card className="ax-col--6" title="Demandes et devis" eyebrow="Fonctionnement">
            <div className="jf-form">
              <Field
                id="max_quotes"
                label="Devis maximum par demande"
                hint="Au-delà, la demande ne reçoit plus de devis : le client compare sans être noyé, les pros ne se battent pas au moins-disant."
              >
                <input
                  id="max_quotes"
                  name="max_quotes"
                  type="number"
                  min={1}
                  max={10}
                  required
                  className="ax-input"
                  defaultValue={s.max_quotes}
                />
              </Field>
              <Field
                id="stale"
                label="Alerte « sans devis » après (heures)"
                hint="Une demande sans aucun devis passé ce délai remonte dans « À traiter »."
              >
                <input
                  id="stale"
                  name="stale_after_hours"
                  type="number"
                  min={1}
                  max={168}
                  required
                  className="ax-input"
                  defaultValue={s.stale_after_hours}
                />
              </Field>
            </div>
          </Card>

          <Card className="ax-col--6" title="Ouverture" eyebrow="Nouvelles demandes">
            <div className="jf-form">
              <Check
                name="accepting_requests"
                label="Les clients peuvent publier de nouvelles demandes"
                checked={s.accepting_requests}
                hint="Décocher pour une pause (fête, saturation des pros). Les demandes en cours continuent."
              />
              <Field
                id="closed_message"
                label="Message affiché pendant la pause"
                wide
                hint={`Ex.${NBSP}: Jeflink fait une pause pour la Tabaski, retour lundi.`}
              >
                <input
                  id="closed_message"
                  name="closed_message"
                  className="ax-input"
                  maxLength={200}
                  defaultValue={s.closed_message}
                />
              </Field>
            </div>
          </Card>

          <Card className="ax-col--12" title="Support" eyebrow="Contact des clients et des pros">
            <div className="jf-form">
              <Field
                id="whatsapp"
                label="WhatsApp du support"
                hint="Bouton WhatsApp du site sur téléphone. Vide : le bouton n'apparaît pas."
              >
                <input
                  id="whatsapp"
                  name="support_whatsapp"
                  className="ax-input"
                  inputMode="tel"
                  placeholder="77 123 45 67"
                  defaultValue={s.support_whatsapp}
                />
              </Field>
              <Field id="email" label="Email du support">
                <input
                  id="email"
                  name="support_email"
                  type="email"
                  className="ax-input"
                  defaultValue={s.support_email}
                />
              </Field>
            </div>
          </Card>
        </div>
        <div className="jf-sticky-save">
          <Submit>Enregistrer les réglages</Submit>
        </div>
      </ActionForm>
    </>
  );
}
