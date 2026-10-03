"use client";

// Pas de temps réel en V1 (ni Channels, ni push) : le client actualise à la main, une requête de
// rendu serveur, sans rechargement complet. Libellé et état en texte.
import { useTranslations } from "next-intl";
import { useRouter } from "next/navigation";
import { useTransition } from "react";

import { Button } from "@/components/ui/button";

export function RefreshButton({ className = "" }: { className?: string }) {
  const t = useTranslations("requests.detail");
  const router = useRouter();
  const [pending, start] = useTransition();
  return (
    <Button
      variant="secondary"
      disabled={pending}
      aria-busy={pending}
      onClick={() => start(() => router.refresh())}
      className={className}
    >
      {pending ? t("refreshing") : t("refresh")}
    </Button>
  );
}
