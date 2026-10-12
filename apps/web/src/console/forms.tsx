/** Formulaires de la console (catalogue, marketing) : champs vireo (.ax-field), envoi par `consoleAction`. */
import { cloneElement, isValidElement, type ReactElement, type ReactNode } from "react";

import { ActionForm } from "./kit";
import { Submit } from "./submit";
import type { CampaignAdmin, CouponAdmin, TradeAdmin, ZoneAdmin } from "./types";

const NBSP = " ";

export function Field({
  id,
  label,
  hint,
  children,
  wide = false,
}: {
  id: string;
  label: ReactNode;
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

/** Liste de cases à cocher envoyée en tableau (`nom[]`) : vide = aucune restriction. */
function Picks({
  name,
  legend,
  hint,
  options,
  checked,
}: {
  name: string;
  legend: string;
  hint: string;
  options: { slug: string; name: string }[];
  checked: string[];
}) {
  return (
    <fieldset className="jf-form__wide jf-picks">
      <legend className="ax-field__label">{legend}</legend>
      <div className="jf-picks__list">
        {options.map((o) => (
          <label key={o.slug}>
            <input
              type="checkbox"
              name={`${name}[]`}
              value={o.slug}
              defaultChecked={checked.includes(o.slug)}
            />
            {o.name}
          </label>
        ))}
      </div>
      <p className="ax-field__hint">{hint}</p>
    </fieldset>
  );
}

export function CouponForm({
  coupon,
  trades,
  zones,
  back,
  prefix,
}: {
  coupon?: CouponAdmin;
  trades: { slug: string; name: string }[];
  zones: { slug: string; name: string }[];
  back: string;
  prefix: string;
}) {
  const id = (name: string) => `${prefix}-${name}`;
  return (
    <ActionForm
      endpoint={coupon ? `/api/console/coupons/${coupon.id}/update/` : "/api/console/coupons/"}
      back={back}
      ok={coupon ? "Code promo enregistré." : "Code promo créé."}
      className="jf-form"
    >
      <Field
        id={id("code")}
        label="Code"
        hint={
          coupon
            ? "Le code ne change pas une fois créé."
            : "3 à 20 lettres ou chiffres, sans espace."
        }
      >
        <input
          id={id("code")}
          name="code"
          className="ax-input jf-code"
          required
          maxLength={20}
          defaultValue={coupon?.code}
          readOnly={Boolean(coupon)}
          placeholder="CLIM20"
          autoCapitalize="characters"
        />
      </Field>
      <Field id={id("description")} label="Description (pour l'équipe et les campagnes)">
        <input
          id={id("description")}
          name="description"
          className="ax-input"
          maxLength={160}
          defaultValue={coupon?.description}
        />
      </Field>
      <Field id={id("kind")} label="Type de remise">
        <select
          id={id("kind")}
          name="kind"
          className="ax-select"
          defaultValue={coupon?.kind ?? "fixed"}
        >
          <option value="fixed">Montant fixe (F CFA)</option>
          <option value="percent">Pourcentage du devis</option>
        </select>
      </Field>
      <Field id={id("value")} label="Valeur (F CFA ou %)" hint="Selon le type choisi.">
        <input
          id={id("value")}
          name="value"
          className="ax-input"
          inputMode="numeric"
          required
          defaultValue={coupon?.value}
        />
      </Field>
      <Field
        id={id("max")}
        label="Remise maximum (F CFA)"
        hint="Pour un pourcentage ; vide = sans plafond."
      >
        <input
          id={id("max")}
          name="max_discount"
          className="ax-input"
          inputMode="numeric"
          defaultValue={coupon?.max_discount ?? ""}
        />
      </Field>
      <Field id={id("min")} label="Devis minimum (F CFA)" hint="Vide = pas de minimum.">
        <input
          id={id("min")}
          name="min_amount"
          className="ax-input"
          inputMode="numeric"
          defaultValue={coupon?.min_amount ?? ""}
        />
      </Field>
      <Field id={id("start")} label="Valable à partir du" hint="Vide = tout de suite.">
        <input
          id={id("start")}
          name="starts_on"
          type="date"
          className="ax-input"
          defaultValue={coupon?.starts_on ?? ""}
        />
      </Field>
      <Field id={id("end")} label="Jusqu'au (inclus)" hint="Vide = sans fin.">
        <input
          id={id("end")}
          name="ends_on"
          type="date"
          className="ax-input"
          defaultValue={coupon?.ends_on ?? ""}
        />
      </Field>
      <Field id={id("uses")} label="Utilisations maximum (au total)" hint="Vide = sans limite.">
        <input
          id={id("uses")}
          name="max_uses"
          className="ax-input"
          inputMode="numeric"
          defaultValue={coupon?.max_uses ?? ""}
        />
      </Field>
      <Field id={id("per")} label="Utilisations par client">
        <input
          id={id("per")}
          name="max_uses_per_client"
          type="number"
          min={1}
          max={50}
          className="ax-input"
          defaultValue={coupon?.max_uses_per_client ?? 1}
        />
      </Field>
      <Picks
        name="trades"
        legend="Métiers concernés"
        hint="Aucun coché = tous les métiers."
        options={trades}
        checked={coupon?.trades.map((t) => t.slug) ?? []}
      />
      <Picks
        name="zones"
        legend="Quartiers concernés"
        hint="Aucun coché = tous les quartiers."
        options={zones}
        checked={coupon?.zones.map((z) => z.slug) ?? []}
      />
      <Check
        name="first_order_only"
        label="Réservé à la première commande d'un client"
        checked={coupon?.first_order_only ?? false}
      />
      <Check
        name="is_active"
        label="Actif"
        checked={coupon?.is_active ?? true}
        hint={`La remise est financée par Jeflink${NBSP}: le pro touche son devis complet.`}
      />
      <div className="jf-form__wide">
        <Submit>{coupon ? "Enregistrer" : "Créer le code"}</Submit>
      </div>
    </ActionForm>
  );
}

export function CampaignForm({
  campaign,
  back,
  prefix,
}: {
  campaign?: CampaignAdmin;
  back: string;
  prefix: string;
}) {
  const id = (name: string) => `${prefix}-${name}`;
  return (
    <ActionForm
      endpoint={
        campaign ? `/api/console/campaigns/${campaign.id}/update/` : "/api/console/campaigns/"
      }
      back={back}
      ok={campaign ? "Campagne enregistrée." : "Campagne créée."}
      className="jf-form"
    >
      <Field id={id("title")} label="Titre">
        <input
          id={id("title")}
          name="title"
          className="ax-input"
          required
          maxLength={80}
          defaultValue={campaign?.title}
        />
      </Field>
      <Field id={id("placement")} label="Où l'afficher">
        <select
          id={id("placement")}
          name="placement"
          className="ax-select"
          defaultValue={campaign?.placement ?? "home"}
        >
          <option value="home">Accueil du site</option>
          <option value="request">Formulaire de demande</option>
          <option value="both">Les deux</option>
        </select>
      </Field>
      <Field id={id("message")} label="Message" wide>
        <input
          id={id("message")}
          name="message"
          className="ax-input"
          required
          maxLength={200}
          defaultValue={campaign?.message}
        />
      </Field>
      <Field id={id("cta")} label="Texte du bouton" hint="Vide = pas de bouton.">
        <input
          id={id("cta")}
          name="cta_label"
          className="ax-input"
          maxLength={40}
          defaultValue={campaign?.cta_label}
        />
      </Field>
      <Field
        id={id("url")}
        label="Page du bouton"
        hint={`Une page du site, ex.${NBSP}: /metiers/menage`}
      >
        <input
          id={id("url")}
          name="cta_url"
          className="ax-input"
          maxLength={200}
          defaultValue={campaign?.cta_url}
        />
      </Field>
      <Field id={id("coupon")} label="Code promo à afficher" hint="Facultatif.">
        <input
          id={id("coupon")}
          name="coupon_code"
          className="ax-input jf-code"
          maxLength={20}
          defaultValue={campaign?.coupon_code}
        />
      </Field>
      <Field id={id("start")} label="Du" hint="Vide = tout de suite.">
        <input
          id={id("start")}
          name="starts_on"
          type="date"
          className="ax-input"
          defaultValue={campaign?.starts_on ?? ""}
        />
      </Field>
      <Field id={id("end")} label="Au (inclus)" hint="Vide = sans fin.">
        <input
          id={id("end")}
          name="ends_on"
          type="date"
          className="ax-input"
          defaultValue={campaign?.ends_on ?? ""}
        />
      </Field>
      <Check name="is_active" label="Active" checked={campaign?.is_active ?? true} />
      <div className="jf-form__wide">
        <Submit className="ax-btn ax-btn--primary ax-btn--sm">
          {campaign ? "Enregistrer" : "Créer la campagne"}
        </Submit>
      </div>
    </ActionForm>
  );
}
