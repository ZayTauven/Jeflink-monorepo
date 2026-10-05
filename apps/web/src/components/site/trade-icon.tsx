// Pictogrammes des métiers, par `icon_key` (spec 002), en SVG en ligne : aucun fichier à
// télécharger. Un `icon_key` absent ou inconnu prend le pictogramme générique, pour qu'un nouveau
// métier s'affiche sans déploiement. Toujours suivi du libellé (voir TradeLabel).
import type { ReactNode, SVGProps } from "react";

import { Icon } from "@/components/ui/icons";

const PATHS: Readonly<Record<string, ReactNode>> = {
  plumbing: <path d="M12 3.5s6 6.2 6 10.5a6 6 0 0 1-12 0c0-4.3 6-10.5 6-10.5Z" />,
  electricity: <path d="M13 2.5 5 13.5h6l-1 8 8-11h-6Z" />,
  cooling: (
    <>
      <path d="M12 3v18M4.2 7.5l15.6 9M4.2 16.5l15.6-9" />
      <path d="m9.5 5 2.5 2.5L14.5 5M9.5 19l2.5-2.5 2.5 2.5" />
    </>
  ),
  appliance: (
    <>
      <rect x="4.5" y="2.5" width="15" height="19" rx="2.5" />
      <circle cx="12" cy="13.5" r="4.5" />
      <path d="M8 6h.01M11 6h.01" />
    </>
  ),
  cleaning: (
    <>
      <path d="M11 3.5c.6 4.4 2.1 5.9 6.5 6.5-4.4.6-5.9 2.1-6.5 6.5-.6-4.4-2.1-5.9-6.5-6.5 4.4-.6 5.9-2.1 6.5-6.5Z" />
      <path d="M18.5 16.5v4M16.5 18.5h4" />
    </>
  ),
  handyman: (
    <path d="M15 4.5a4.5 4.5 0 0 0-4 6.3L4 17.8a1.8 1.8 0 0 0 2.5 2.5l7-7A4.5 4.5 0 0 0 19.5 9l-2.7 2.7-2.5-.5-.5-2.5Z" />
  ),
};

const GENERIC = (
  <>
    <rect x="3.5" y="8" width="17" height="11.5" rx="2.5" />
    <path d="M9 8V6.5A1.5 1.5 0 0 1 10.5 5h3A1.5 1.5 0 0 1 15 6.5V8M3.5 13h17" />
  </>
);

/** Le pictogramme du métier, ou le générique. Décoratif (`aria-hidden`) : le libellé porte le sens. */
export function TradeIcon({
  iconKey,
  ...props
}: SVGProps<SVGSVGElement> & { iconKey: string | null | undefined }) {
  const known = iconKey && Object.hasOwn(PATHS, iconKey) ? PATHS[iconKey] : null;
  return <Icon {...props}>{known ?? GENERIC}</Icon>;
}
