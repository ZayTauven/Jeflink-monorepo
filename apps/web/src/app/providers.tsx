"use client";

// Client API du navigateur (spec 001, « BFF Next ») : même origine (le BFF), cookies httpOnly,
// aucun jeton côté JavaScript. Un 401 déclenche un seul refresh, sous le verrou partagé entre
// onglets (@jeflink/api-client/web). Une fin de session, dans cet onglet ou un autre, vide le
// cache puis recharge : la connexion si la session a expiré, l'accueil après une déconnexion.
//
// Pas de `useSuspenseQuery` sans préchargement serveur : la requête partirait au rendu serveur,
// sans session ni transport.
import { configureApiClient } from "@jeflink/api-client";
import { safeNextPath } from "@jeflink/api-client/paths";
import { onWebSessionEnded, refreshWebSession } from "@jeflink/api-client/web";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { type ReactNode, useEffect, useState } from "react";

import { LOGIN_PATH } from "../lib/routes.ts";
import { isLoginPath } from "../lib/session-redirects.ts";

// Une seule fois, au chargement du module, dans le navigateur seulement : au rendu serveur, le
// singleton du module ne reçoit rien (S4). Jamais de `baseUrl` absolue.
if (typeof window !== "undefined") {
  configureApiClient({
    baseUrl: "",
    getLanguage: () => document.documentElement.lang || "fr",
    onUnauthorized: () => refreshWebSession(),
  });
}

export function Providers({ children }: { children: ReactNode }) {
  // Un client par montage : au rendu serveur, jamais partagé entre deux requêtes.
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          // Réseau faible : pas de rafale de requêtes au retour sur l'onglet.
          queries: { refetchOnWindowFocus: false, retry: 1 },
        },
      }),
  );

  useEffect(
    () =>
      onWebSessionEnded((reason) => {
        queryClient.clear();
        // Navigation complète : cache du routeur, brouillons en mémoire et retour arrière purgés
        // (téléphone partagé, T2 ; revue web 1, m-1). Jamais depuis la connexion elle-même.
        const here = safeNextPath(`${window.location.pathname}${window.location.search}`);
        if (isLoginPath(here)) return;
        window.location.replace(
          reason === "expired" ? `${LOGIN_PATH}?next=${encodeURIComponent(here)}` : "/",
        );
      }),
    [queryClient],
  );

  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}
