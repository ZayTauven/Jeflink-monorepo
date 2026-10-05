// Espace client (/connexion, /demande, /compte) : sessions, formulaires, React Query. C'est le seul
// groupe qui embarque `Providers` et tous les messages côté client ; le site public n'en veut pas
// (budget JS, spec 006). Les URL ne changent pas : un groupe de routes n'ajoute pas de segment.
import { NextIntlClientProvider } from "next-intl";
import type { ReactNode } from "react";

import { Providers } from "./providers";

export default function EspaceLayout({ children }: { children: ReactNode }) {
  return (
    <NextIntlClientProvider>
      <Providers>{children}</Providers>
    </NextIntlClientProvider>
  );
}
