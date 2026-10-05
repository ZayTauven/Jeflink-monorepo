// Site public : en-tête, contenu, pied de page (voir SiteChrome). Une page de ce groupe ne lit
// jamais la session (ni cookies, ni en-têtes du visiteur) : son HTML est le même pour tous
// (ADR 0013). Les données passent par `publicApi()`, jamais par `serverApi()` (test d'architecture).
import type { ReactNode } from "react";

import { SiteChrome } from "@/components/site/site-chrome";

export default function SiteLayout({ children }: { children: ReactNode }) {
  return <SiteChrome>{children}</SiteChrome>;
}
