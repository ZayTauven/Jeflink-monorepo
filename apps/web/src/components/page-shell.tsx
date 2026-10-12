import type { ReactNode } from "react";

import { MobileActions } from "./mobile-actions";
import { SiteFooter } from "./site-footer";
import { SiteHeader } from "./site-header";

/** Gabarit commun : en-tête, contenu, pied de page Crafto, barre d'actions mobile. */
export function PageShell({
  children,
  home = false,
  actions = true,
}: {
  children: ReactNode;
  home?: boolean;
  actions?: boolean;
}) {
  return (
    <>
      <SiteHeader bordered={home} />
      {children}
      <SiteFooter />
      {actions && <MobileActions />}
    </>
  );
}
