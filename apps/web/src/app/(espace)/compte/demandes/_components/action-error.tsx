"use client";

// Erreur d'une action sur la réservation : un libellé par code (`bookings.errors`), et toujours une
// sortie : « Actualiser » quand la page est périmée, le support WhatsApp quand rien ne se règle seul.
import { useTranslations } from "next-intl";

import { Alert } from "@/components/ui/alert";
import { ButtonLink } from "@/components/ui/button";
import { ChatIcon } from "@/components/ui/icons";
import { isStale } from "@/lib/bookings/errors";
import type { RequestError } from "@/lib/requests/errors";

import { RefreshButton } from "./refresh-button";

export function ActionError({
  error,
  supportHref,
}: {
  error: RequestError;
  supportHref: string | null;
}) {
  const t = useTranslations("bookings.errors");
  const tCommon = useTranslations("bookings.common");
  let action = undefined;
  if (isStale(error.code)) action = <RefreshButton />;
  else if (error.support && supportHref) {
    action = (
      <ButtonLink
        href={supportHref}
        target="_blank"
        rel="noopener noreferrer"
        variant="secondary"
        className="self-start"
      >
        <ChatIcon className="size-5" />
        {tCommon("writeSupport")}
      </ButtonLink>
    );
  }
  return (
    <Alert tone="error" action={action}>
      {t(error.key, error.values)}
    </Alert>
  );
}
