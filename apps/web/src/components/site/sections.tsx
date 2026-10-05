// Briques de page du site public, partagées par l'accueil, les pages métier et les pages sœurs.
// Composants serveur. Les valeurs chiffrées (nombre de devis, délais) viennent de `rules` (API) et
// jamais de la copie ; sans `rules` (API en panne), la phrase correspondante perd son chiffre.
import type { PublicRules } from "@jeflink/api-client";
import { getTranslations } from "next-intl/server";
import type { ReactNode } from "react";

import { CheckIcon } from "@/components/ui/icons";

import { SectionNumber } from "./section-number";

export type Rules = PublicRules | null | undefined;

const pill =
  "inline-flex min-h-8 items-center rounded-pill bg-accent px-4 text-sm font-medium text-on-accent";

/** Section de page : fond `paper` ou `sand` (alternance Crafto), largeur et marges communes. */
export function Section({
  id,
  title,
  lead,
  tone = "paper",
  children,
  className = "",
}: {
  id?: string;
  title?: ReactNode;
  lead?: ReactNode;
  tone?: "paper" | "sand";
  children?: ReactNode;
  className?: string;
}) {
  const headingId = id ? `${id}-titre` : undefined;
  return (
    <section
      id={id}
      aria-labelledby={title ? headingId : undefined}
      className={`${tone === "sand" ? "bg-sand" : "bg-paper"} ${className}`}
    >
      <div className="mx-auto max-w-6xl px-4 py-12 sm:px-6 sm:py-20">
        {title ? (
          <h2
            id={headingId}
            className="font-display text-balance text-3xl leading-[1.05] tracking-tight sm:text-5xl"
          >
            {title}
          </h2>
        ) : null}
        {lead ? <p className="mt-4 max-w-2xl text-lg text-ink-muted">{lead}</p> : null}
        {children ? <div className={title || lead ? "mt-8 sm:mt-10" : ""}>{children}</div> : null}
      </div>
    </section>
  );
}

/** Titre de page en deux blocs (Crafto) : carte blanche avec pastille et titre, puis l'image. */
export function PageHeader({
  kicker,
  title,
  lead,
  actions,
  media,
}: {
  /** Pastille au-dessus du titre : seulement si elle apporte une information que le titre n'a pas. */
  kicker?: string;
  title: string;
  lead?: string;
  actions?: ReactNode;
  media?: ReactNode;
}) {
  return (
    <header className="mx-auto max-w-6xl px-4 pb-4 pt-6 sm:px-6 sm:pt-10">
      <div className="grid gap-4 lg:grid-cols-2">
        <div className="flex flex-col items-start gap-5 rounded-card border border-line bg-surface p-6 sm:p-10">
          {kicker ? <p className={pill}>{kicker}</p> : null}
          <h1 className="font-display text-balance text-4xl leading-[1.05] tracking-tight sm:text-6xl">
            {title}
          </h1>
          {lead ? <p className="text-lg text-ink-muted">{lead}</p> : null}
          {actions}
        </div>
        {media ? <div>{media}</div> : null}
      </div>
    </header>
  );
}

export type Row = { id: string; title: string; text?: string };

/** Rangées bordées 1 px (Crafto « liste des prix », format repris pour les points forts). */
export function ValueRows({
  items,
  className = "",
}: {
  items: readonly Row[];
  className?: string;
}) {
  return (
    <ul className={`border-t border-line ${className}`}>
      {items.map((item) => (
        <li
          key={item.id}
          className="grid gap-2 border-b border-line py-5 sm:grid-cols-[1fr_2fr] sm:gap-8 sm:py-6"
        >
          <h3 className="font-display text-2xl tracking-tight">{item.title}</h3>
          {item.text ? <p className="text-base text-ink-muted">{item.text}</p> : null}
        </li>
      ))}
    </ul>
  );
}

/** Liste à coches : une ligne = un fait (« Ce que nous vérifions », garanties). */
export function CheckList({
  items,
  className = "",
}: {
  items: readonly string[];
  className?: string;
}) {
  return (
    <ul className={`border-t border-line ${className}`}>
      {items.map((text) => (
        <li key={text} className="flex items-start gap-3 border-b border-line py-4 text-base">
          <CheckIcon className="mt-0.5 size-5 shrink-0 text-accent-strong" />
          <span>{text}</span>
        </li>
      ))}
    </ul>
  );
}

/** « Comment ça marche » en 3 étapes numérotées (liste ordonnée). */
export async function HowSection({
  rules,
  tone = "paper",
}: {
  rules: Rules;
  tone?: "paper" | "sand";
}) {
  const t = await getTranslations("site.how");
  const steps = [
    { id: "one", title: t("steps.one.title"), text: t("steps.one.text") },
    {
      id: "two",
      title: rules
        ? t("steps.two.title", { count: rules.max_quotes_per_request })
        : t("steps.two.titleNoRules"),
      text: t("steps.two.text"),
    },
    { id: "three", title: t("steps.three.title"), text: t("steps.three.text") },
  ];
  return (
    <Section id="comment-ca-marche" title={t("title")} tone={tone}>
      <ol className="grid gap-8 md:grid-cols-3">
        {steps.map((step, index) => (
          <li key={step.id} className="flex flex-col gap-3">
            <SectionNumber number={index + 1} />
            <h3 className="font-display text-2xl tracking-tight">{step.title}</h3>
            <p className="text-base text-ink-muted">{step.text}</p>
          </li>
        ))}
      </ol>
    </Section>
  );
}

/** « Quand le pro vient-il ? » : les règles réelles, valeurs de `rules`. */
export async function WhenSection({
  rules,
  tone = "paper",
}: {
  rules: Rules;
  tone?: "paper" | "sand";
}) {
  const t = await getTranslations("site.when");
  return (
    <Section id="quand-le-pro-vient" title={t("title")} tone={tone}>
      <div className="max-w-2xl space-y-3 text-lg">
        <p>{t("slot")}</p>
        {rules ? (
          <>
            <p>
              {t("confirm", {
                hours: rules.pro_confirm_hours,
                urgent: rules.pro_confirm_hours_urgent,
              })}
            </p>
            <p className="text-ink-muted">{t("night")}</p>
          </>
        ) : null}
      </div>
    </Section>
  );
}

export async function GuaranteesList({ rules }: { rules: Rules }) {
  const t = await getTranslations("site.guarantees");
  return (
    <CheckList
      items={[
        t("verified"),
        t("price"),
        t("code"),
        rules ? t("dispute", { hours: rules.dispute_window_hours }) : t("disputeNoRules"),
      ]}
    />
  );
}

export async function NeverList() {
  const t = await getTranslations("site.never");
  return <CheckList items={[t("money"), t("code"), t("more")]} />;
}

/** Ce que nous vérifions : la procédure réelle seulement (Q7, à écrire dans docs/ops). */
export async function VerifyList() {
  const t = await getTranslations("site.about.verify");
  return <CheckList items={[t("identity"), t("phone"), t("reference")]} />;
}
