"use client";

// Erreur de chargement : un message clair et « Réessayer », jamais une page blanche. Aucune
// trace ni détail technique affiché ; la demande, elle, n'est pas perdue.
import { useTranslations } from "next-intl";

import { PageShell } from "@/components/page-shell";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";

export default function RequestsError({ retry }: { error: Error; retry: () => void }) {
  const t = useTranslations("requests.failure");
  return (
    <PageShell>
      <Alert
        tone="error"
        action={
          <Button variant="secondary" onClick={() => retry()} className="self-start">
            {t("retry")}
          </Button>
        }
      >
        <p className="font-medium">{t("title")}</p>
        <p>{t("lead")}</p>
      </Alert>
    </PageShell>
  );
}
