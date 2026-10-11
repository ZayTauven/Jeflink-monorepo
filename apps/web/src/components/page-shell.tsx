import type { ReactNode } from "react";

import { SiteFooter } from "./site-footer";
import { SiteHeader } from "./site-header";

/** Gabarit commun : en-tête, contenu, pied de page Crafto. */
export function PageShell({ children, home = false }: { children: ReactNode; home?: boolean }) {
  return (
    <>
      <SiteHeader bordered={home} />
      {children}
      <SiteFooter />
    </>
  );
}
