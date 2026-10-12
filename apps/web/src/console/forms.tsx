/** Formulaires de la console (catalogue) : champs vireo (.ax-field), envoi par `consoleAction`. */
import { cloneElement, isValidElement, type ReactElement, type ReactNode } from "react";

import { ActionForm } from "./kit";
import { Submit } from "./submit";
import type { TradeAdmin, ZoneAdmin } from "./types";

const NBSP = " ";

export function Field({
  id,
  label,
  hint,
  children,
  wide = false,
}: {
  id: string;
  label: string;
  hint?: ReactNode;
  children: ReactNode;
  wide?: boolean;
}) {
  return (
    <div className={`ax-field${wide ? " jf-form__wide" : ""}`}>
      <label className="ax-field__label" htmlFor={id}>
        {label}
      </label>
      {hint && isValidElement(children)
        ? cloneElement(children as ReactElement<{ "aria-describedby"?: string }>, {
            "aria-describedby": `${id}-aide`,
          })
        : children}
      {hint && (
        <p className="ax-field__hint" id={`${id}-aide`}>
          {hint}
        </p>
      )}
    </div>
  );
}

/** Case à cocher envoyée même décochée (« 0 » caché, puis « 1 » si cochée). */
export function Check({
  name,
  label,
  checked,
  hint,
}: {
  name: string;
  label: string;
  checked: boolean;
  hint?: string;
}) {
  return (
    <div className="jf-form__wide jf-check">
      <input type="hidden" name={name} value="0" />
      <label>
        <input
          type="checkbox"
          name={name}
          value="1"
          defaultChecked={checked}
          aria-describedby={hint ? `${name}-aide` : undefined}
        />
        {label}
      </label>
      {hint && (
        <p className="ax-field__hint" id={`${name}-aide`}>
          {hint}
        </p>
      )}
    </div>
  );
}

export function TradeForm({
  trade,
  back,
  prefix,
}: {
  trade?: TradeAdmin;
  back: string;
  prefix: string;
}) {
  const id = (name: string) => `${prefix}-${name}`;
  return (
    <ActionForm
      endpoint={trade ? `/api/console/trades/${trade.id}/update/` : "/api/console/trades/"}
      back={back}
      ok={trade ? "Métier enregistré." : "Métier créé."}
      className="jf-form"
    >
      <Field id={id("name")} label="Nom du métier">
        <input
          id={id("name")}
          name="name"
          className="ax-input"
          required
          maxLength={80}
          defaultValue={trade?.name}
        />
      </Field>
      <Field id={id("tagline")} label="Résumé (cartes du site)">
        <input
          id={id("tagline")}
          name="tagline"
          className="ax-input"
          maxLength={180}
          defaultValue={trade?.tagline}
          placeholder={`Ex.${NBSP}: fuites, débouchage, chauffe-eau, pompes.`}
        />
      </Field>
      <Field id={id("description")} label="Présentation (page du métier)" wide>
        <textarea
          id={id("description")}
          name="description"
          className="ax-textarea"
          rows={3}
          defaultValue={trade?.description}
        />
      </Field>
      <Field id={id("services")} label="Prestations courantes" hint="Une par ligne." wide>
        <textarea
          id={id("services")}
          name="services"
          className="ax-textarea"
          rows={5}
          defaultValue={trade?.services.join("\n")}
        />
      </Field>
      <Field
        id={id("price")}
        label="À partir de (F CFA)"
        hint="Montant entier ; vide = pas de prix affiché."
      >
        <input
          id={id("price")}
          name="starting_price"
          className="ax-input"
          inputMode="numeric"
          defaultValue={trade?.starting_price ?? ""}
          placeholder="5000"
        />
      </Field>
      <Field
        id={id("icon")}
        label="Icône"
        hint={
          <>
            Nom Bootstrap Icons, ex.{NBSP}: <code>bi-droplet</code>
            {trade?.icon && (
              <>
                {" "}
                · aperçu{NBSP}: <i className={`bi ${trade.icon}`} aria-hidden="true" />
              </>
            )}
          </>
        }
      >
        <input id={id("icon")} name="icon" className="ax-input" defaultValue={trade?.icon} />
      </Field>
      <Field
        id={id("image")}
        label="Image"
        hint={`Chemin d'une image du site, ex.${NBSP}: /images/metiers/plomberie.webp`}
      >
        <input id={id("image")} name="image" className="ax-input" defaultValue={trade?.image} />
      </Field>
      <Field id={id("position")} label="Ordre d'affichage" hint="Les plus petits d'abord.">
        <input
          id={id("position")}
          name="position"
          type="number"
          min={0}
          max={999}
          className="ax-input"
          defaultValue={trade?.position ?? 0}
        />
      </Field>
      <Check
        name="is_active"
        label="Proposé sur le site"
        checked={trade?.is_active ?? true}
        hint="Décoché : le métier disparaît du site et des nouvelles demandes ; l'historique reste."
      />
      <div className="jf-form__wide">
        <Submit>{trade ? "Enregistrer" : "Créer le métier"}</Submit>
      </div>
    </ActionForm>
  );
}

export function ZoneForm({
  zone,
  back,
  prefix,
}: {
  zone?: ZoneAdmin;
  back: string;
  prefix: string;
}) {
  const id = (name: string) => `${prefix}-${name}`;
  return (
    <ActionForm
      endpoint={zone ? `/api/console/zones/${zone.id}/update/` : "/api/console/zones/"}
      back={back}
      ok={zone ? "Quartier enregistré." : "Quartier ajouté."}
      className="jf-form"
    >
      <Field id={id("name")} label="Quartier ou commune">
        <input
          id={id("name")}
          name="name"
          className="ax-input"
          required
          maxLength={80}
          defaultValue={zone?.name}
        />
      </Field>
      <Field id={id("city")} label="Ville">
        <input
          id={id("city")}
          name="city"
          className="ax-input"
          required
          maxLength={80}
          defaultValue={zone?.city ?? "Dakar"}
        />
      </Field>
      <Field id={id("position")} label="Ordre d'affichage">
        <input
          id={id("position")}
          name="position"
          type="number"
          min={0}
          max={999}
          className="ax-input"
          defaultValue={zone?.position ?? 0}
        />
      </Field>
      <Check name="is_active" label="Desservi" checked={zone?.is_active ?? true} />
      <div className="jf-form__wide">
        <Submit className="ax-btn ax-btn--primary ax-btn--sm">
          {zone ? "Enregistrer" : "Ajouter le quartier"}
        </Submit>
      </div>
    </ActionForm>
  );
}
