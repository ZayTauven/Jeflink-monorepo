// Source unique des design tokens Jeflink (voir docs/design/DESIGN.md).
// Les CSS de generated/ sont produits depuis ce fichier : `pnpm --filter @jeflink/ui-tokens build`.

export type ColorToken =
  | "ink"
  | "ink-muted"
  | "paper"
  | "sand"
  | "surface"
  | "line"
  | "line-strong"
  | "accent"
  | "on-accent"
  | "accent-strong"
  | "on-accent-strong"
  | "success"
  | "warning"
  | "danger"
  | "info";

export type Palette = Readonly<Record<ColorToken, string>>;

/** Thème clair : web public, apps mobiles, console par défaut. */
export const light: Palette = {
  ink: "#14171C",
  "ink-muted": "#5B6270",
  paper: "#FAF8F4",
  sand: "#EDECE3",
  surface: "#FFFFFF",
  line: "#E6E1D8",
  "line-strong": "#85817A",
  accent: "#FF6600",
  "on-accent": "#14171C",
  "accent-strong": "#B84800",
  "on-accent-strong": "#FFFFFF",
  success: "#15803D",
  warning: "#A16207",
  danger: "#B91C1C",
  info: "#1D6FB8",
};

/** Thème sombre : console uniquement en V1. Mêmes noms, valeurs redéfinies. */
export const dark: Palette = {
  ink: "#F2F0EB",
  "ink-muted": "#A3A9B5",
  paper: "#111317",
  sand: "#20252D",
  surface: "#1B1F26",
  line: "#2E3440",
  "line-strong": "#6B7280",
  accent: "#FF6600",
  "on-accent": "#14171C",
  "accent-strong": "#FF8A3D",
  "on-accent-strong": "#14171C",
  success: "#4ADE80",
  warning: "#FACC15",
  danger: "#F87171",
  info: "#60A5FA",
};

export const radius = {
  /** Cartes, champs, images. */
  card: "10px",
  /** Boutons, puces, filtres. */
  pill: "999px",
} as const;

/** Une seule élévation, réservée aux overlays (menus, modales, popovers). */
export const shadow = {
  overlay: "0 8px 24px rgb(20 23 28 / 0.12)",
} as const;

/**
 * Familles. Chaque app charge les fichiers (next/font côté web, expo-font côté mobile)
 * et expose la police chargée via --font-funnel-display / --font-inter (ex. option `variable`
 * de next/font) ; sinon repli sur le nom de famille puis la police système.
 */
export const font = {
  display: {
    family: "Funnel Display",
    stack: 'var(--font-funnel-display, "Funnel Display"), ui-sans-serif, system-ui, sans-serif',
  },
  text: {
    family: "Inter",
    stack: 'var(--font-inter, "Inter"), ui-sans-serif, system-ui, sans-serif',
  },
} as const;

/**
 * Paires texte/fond qui doivent tenir WCAG 2.1 AA, vérifiées au build.
 * min = 4.5 pour du texte, 3 pour un composant d'interface (bordure de champ, focus).
 */
export const contrastPairs: ReadonlyArray<{
  fg: ColorToken;
  bg: ColorToken;
  min: 4.5 | 3;
}> = [
  ...(["paper", "sand", "surface"] as const).flatMap((bg) => [
    { fg: "ink" as const, bg, min: 4.5 as const },
    { fg: "ink-muted" as const, bg, min: 4.5 as const },
    { fg: "line-strong" as const, bg, min: 3 as const },
  ]),
  ...(["paper", "surface"] as const).flatMap((bg) =>
    (["accent-strong", "success", "warning", "danger", "info"] as const).map((fg) => ({
      fg,
      bg,
      min: 4.5 as const,
    })),
  ),
  { fg: "on-accent", bg: "accent", min: 4.5 },
  { fg: "on-accent-strong", bg: "accent-strong", min: 4.5 },
];
