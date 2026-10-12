/** Petits motifs répétés du template Crafto « Marketing strategy », à l'identique. */

import type { ReactNode } from "react";

// --- Animations d'apparition (lues par main.js via data-anime) --------------------------------

const anime = (o: Record<string, unknown>) =>
  JSON.stringify({ duration: 600, delay: 0, staggervalue: 300, easing: "easeOutQuad", ...o });

export const fadeIn = (delay = 0) => anime({ opacity: [0, 1], delay });
export const fadeUp = (delay = 0) => anime({ translateY: [30, 0], opacity: [0, 1], delay });
export const childsUp = (delay = 0) =>
  anime({ el: "childs", translateY: [30, 0], opacity: [0, 1], delay });
export const childsFade = (delay = 0) => anime({ el: "childs", opacity: [0, 1], delay });
export const slideX = (from: number, delay = 600) =>
  anime({ translateX: [from, 0], opacity: [0, 1], delay });
export const lines = (delay = 0, staggervalue = 300) =>
  anime({
    el: "lines",
    translateY: [50, 0],
    translateZ: [-50, 0],
    rotateX: [-80, 0],
    origin: [50, 0],
    opacity: [0, 1],
    delay,
    staggervalue,
  });
export const PERSPECTIVE = { perspective: "400px" } as const;

// --- Boutons « switch » (texte + icône Feather qui glisse) -------------------------------------

function SwitchInner({ label, icon }: { label: ReactNode; icon: string }) {
  return (
    <span>
      <span className="btn-text">{label}</span>
      <span className="btn-icon">
        <i className={`feather ${icon}`} />
      </span>
      <span className="btn-icon">
        <i className={`feather ${icon}`} />
      </span>
    </span>
  );
}

export function SwitchLink({
  href,
  label,
  icon,
  className,
}: {
  href: string;
  label: ReactNode;
  icon: string;
  className: string;
}) {
  return (
    <a href={href} className={`btn btn-hover-animation-switch ${className}`}>
      <SwitchInner label={label} icon={icon} />
    </a>
  );
}

/** Bouton d'envoi de formulaire. Jamais la classe `submit` : main.js l'intercepte. */
export function SwitchSubmit({
  label,
  icon,
  className,
  name,
  value,
}: {
  label: ReactNode;
  icon: string;
  className: string;
  name?: string;
  value?: string;
}) {
  return (
    <button
      type="submit"
      name={name}
      value={value}
      className={`btn btn-hover-animation-switch ${className}`}
    >
      <SwitchInner label={label} icon={icon} />
    </button>
  );
}

// --- Flèche orange en diagonale (survol : elle « glisse ») --------------------------------------

export function ArrowSwipe({
  size,
  svgClassName = "",
  className = "",
}: {
  size: 30 | 40 | 71;
  svgClassName?: string;
  className?: string;
}) {
  const box = size === 40 ? 46 : 71;
  const d = size === 40 ? "M3 3L43 43M43 43V3M43 43H3" : "M4 4L66.5 66.5M66.5 66.5V4M66.5 66.5H4";
  const stroke = size === 40 ? 6 : 8;
  return (
    <div className={`icon-wrap top-to-bottom ${className}`}>
      {["first", "second"].map((k) => (
        <svg
          key={k}
          className={`${k} icon ${svgClassName}`}
          width={size}
          height={size}
          viewBox={`0 0 ${box} ${box}`}
          fill="none"
          aria-hidden="true"
        >
          <path d={d} stroke="#F55608" strokeWidth={stroke} strokeLinecap="round" />
        </svg>
      ))}
    </div>
  );
}

// --- Étiquettes en pilule ---------------------------------------------------------------------

export function Pill({
  children,
  className = "",
  anime,
}: {
  children: ReactNode;
  className?: string;
  anime?: string;
}) {
  return (
    <div
      data-anime={anime}
      className={`fs-12 lh-18 fw-500 text-uppercase border-radius-50px ps-25px pe-25px pt-10px pb-10px d-inline-block ${className}`}
    >
      {children}
    </div>
  );
}

export function Asterisk({
  children,
  className = "",
  anime,
}: {
  children: ReactNode;
  className?: string;
  anime?: string;
}) {
  return (
    <div className={`d-inline-flex align-items-center ${className}`} data-anime={anime}>
      <i className="bi bi-asterisk icon-extra-medium text-base-color me-10px" />
      <span className="alt-font fs-22 sm-fs-20">{children}</span>
    </div>
  );
}

/**
 * Image Crafto servie par l'optimiseur de Next (WebP, sans agrandissement) : les JPG/PNG du
 * template pèsent 10 à 15 fois plus que leur version WebP.
 */
export function opt(src: string, width = 1920): string {
  return `/_next/image?url=${encodeURIComponent(src)}&w=${width}&q=75`;
}

/** Marge latérale commune à toutes les sections du template. */
export const SECTION_X =
  "ps-65px pe-65px xl-ps-45px xl-pe-45px lg-ps-15px lg-pe-15px sm-ps-0 sm-pe-0";
