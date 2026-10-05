"use client";

// Ce que le cadre public sait et que la limite d'erreur (Client Component) ne peut pas lire elle-même :
// le lien WhatsApp du support et les métiers du cache. Valeurs publiques, calculées par le layout.
import { createContext, type ReactNode, useContext } from "react";

export type SiteContextValue = {
  /** Lien `wa.me` du support avec un message générique ; null si le numéro n'est pas configuré. */
  supportHref: string | null;
  trades: readonly { slug: string; name: string }[];
};

const SiteContext = createContext<SiteContextValue>({ supportHref: null, trades: [] });

export function SiteContextProvider({
  value,
  children,
}: {
  value: SiteContextValue;
  children: ReactNode;
}) {
  return <SiteContext.Provider value={value}>{children}</SiteContext.Provider>;
}

export function useSiteContext(): SiteContextValue {
  return useContext(SiteContext);
}
