// Boutons Jeflink (DESIGN.md › Tokens). CTA principal : fond `accent` et libellé `on-accent`
// (sombre, écho au logo noir et orange), le seul des deux choix AA retenu partout. Pilule, cible
// d'au moins 48 px, anneau de focus `accent-strong`.
import type { AnchorHTMLAttributes, ButtonHTMLAttributes } from "react";

type Variant = "primary" | "secondary" | "quiet";

const base =
  "inline-flex min-h-12 items-center justify-center gap-2 rounded-pill px-6 text-base font-medium " +
  "transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 " +
  "focus-visible:outline-accent-strong disabled:cursor-not-allowed disabled:opacity-60";

const variants: Record<Variant, string> = {
  primary: "bg-accent text-on-accent hover:bg-accent-strong hover:text-on-accent-strong",
  secondary: "border border-line-strong bg-surface text-ink hover:border-ink",
  quiet: "text-accent-strong underline underline-offset-4 hover:text-ink",
};

export function buttonClass(variant: Variant = "primary", extra = ""): string {
  return `${base} ${variants[variant]} ${extra}`.trim();
}

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant };

export function Button({
  variant = "primary",
  className = "",
  type = "button",
  ...props
}: ButtonProps) {
  return <button type={type} className={buttonClass(variant, className)} {...props} />;
}

type LinkProps = AnchorHTMLAttributes<HTMLAnchorElement> & { variant?: Variant };

/** Lien habillé en bouton (lien externe WhatsApp, retour à une page). */
export function ButtonLink({ variant = "secondary", className = "", ...props }: LinkProps) {
  return <a className={buttonClass(variant, className)} {...props} />;
}
