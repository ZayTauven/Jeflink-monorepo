"use client";

// Pas de temps réel en V1 (ni Channels, ni push) : le client actualise à la main, une requête de
// rendu serveur, sans rechargement complet. Libellé et état en texte.
import { useTranslations } from "next-intl";
import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";

export function RefreshButton({ className = "" }: { className?: string }) {
  const t = useTranslations("requests.detail");
  const router = useRouter();
  const tErr = useTranslations("requests.errors");
  const [pending, start] = useTransition();
  const [offline, setOffline] = useState(false);
  return (
    <div className="flex flex-col gap-3">
      <Button
        variant="secondary"
        disabled={pending}
        aria-busy={pending}
        onClick={() => {
          // Hors ligne, le rafraîchissement échouerait en silence : on le dit.
          const down = typeof navigator !== "undefined" && navigator.onLine === false;
          setOffline(down);
          if (!down) start(() => router.refresh());
        }}
        className={className}
      >
        {pending ? t("refreshing") : t("refresh")}
      </Button>
      {offline ? <Alert tone="error">{tErr("network")}</Alert> : null}
    </div>
  );
}
