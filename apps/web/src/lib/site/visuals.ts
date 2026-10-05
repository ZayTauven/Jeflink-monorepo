// Visuels du site par `icon_key` (spec 002 : `plumbing`, `electricity`, `cooling`, `appliance`,
// `cleaning`, `handyman`), jamais par slug de métier. Un `icon_key` absent ou inconnu prend le
// visuel générique : un nouveau métier s'affiche sans déploiement. Provenance et licences :
// docs/design/assets.md (toutes « à confirmer », dev local). Module pur.

export type ImageFile = { src: string; width: number; height: number };

export type TradeVisual =
  | {
      kind: "photo";
      /** Clé i18n sous `site.visuals` : le texte de remplacement décrit ce que l'image montre. */
      altKey: string;
      /** Carte (600 px de large). */
      card: ImageFile;
      /** Page métier × quartier sur mobile (480 px de large). */
      compact: ImageFile;
    }
  | { kind: "generic" };

const DIR = "/images/site";

function photo(key: string): TradeVisual {
  return {
    kind: "photo",
    altKey: key,
    card: { src: `${DIR}/metier-${key}-600.webp`, width: 600, height: 450 },
    compact: { src: `${DIR}/metier-${key}-480.webp`, width: 480, height: 360 },
  };
}

/** Pas de photo pour `appliance` (électroménager) : aucune scène humaine dans la banque (Q9). */
const BY_ICON_KEY: Readonly<Record<string, TradeVisual>> = {
  plumbing: photo("plumbing"),
  electricity: photo("electricity"),
  cooling: photo("cooling"),
  cleaning: photo("cleaning"),
  handyman: photo("handyman"),
};

export const GENERIC_VISUAL: TradeVisual = { kind: "generic" };

export function tradeVisual(iconKey: string | null | undefined): TradeVisual {
  if (!iconKey || !Object.hasOwn(BY_ICON_KEY, iconKey)) return GENERIC_VISUAL;
  return BY_ICON_KEY[iconKey] ?? GENERIC_VISUAL;
}

/** Visuels propres au site (hors métiers) : hero, carte « Devenir pro », photo de Dakar. */
export const SITE_IMAGES = {
  hero: {
    altKey: "hero",
    small: { src: `${DIR}/hero-750.webp`, width: 750, height: 938 },
    large: { src: `${DIR}/hero-1600.webp`, width: 1600, height: 2000 },
  },
  pro: { altKey: "pro", image: { src: `${DIR}/pro-600.webp`, width: 600, height: 450 } },
  dakar: { altKey: "dakar", image: { src: `${DIR}/dakar-1200.webp`, width: 1200, height: 800 } },
} as const;
