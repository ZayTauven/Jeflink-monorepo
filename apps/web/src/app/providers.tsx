"use client";

// Client API du navigateur (spec 001, « BFF Next ») : même origine (le BFF), cookies httpOnly,
// aucun jeton côté JavaScript. Un 401 déclenche un seul refresh, sous le verrou partagé entre
// onglets (@jeflink/api-client/web). Une fin de session, annoncée par cet onglet ou un autre,
// vide le cache ; une session expirée renvoie à la connexion.
//
// Pas de `useSuspenseQuery` sans préchargement serveur : la requête partirait au rendu serveur,
// sans session ni transport.
import { configureApiClient } from "@jeflink/api-client";
import { safeNextPath } from "@jeflink/api-client/paths";
import { onWebSessionEnded, refreshWebSession } from "@jeflink/api-client/web";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { type ReactNode, useEffect, useState } from "react";

const LOGIN_PATH = "/connexion";

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
  const router = useRouter();
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
        if (reason === "expired") {
          const here = safeNextPath(`${window.location.pathname}${window.location.search}`);
          router.replace(`${LOGIN_PATH}?next=${encodeURIComponent(here)}`);
        } else {
          router.refresh(); // déconnexion : la page se rend de nouveau, sans session
        }
      }),
    [queryClient, router],
  );

  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}
