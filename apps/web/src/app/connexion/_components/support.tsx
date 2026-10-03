"use client";

// Support WhatsApp et erreurs du parcours (spec 001, T3) : aucune impasse. Le message pré-rempli
// ne contient jamais de code ni de numéro.
import { useTranslations } from "next-intl";
import { createContext, useContext } from "react";

import { Alert } from "@/components/ui/alert";
import { ButtonLink } from "@/components/ui/button";
import { ChatIcon } from "@/components/ui/icons";
import type { LoginError } from "@/lib/login/errors";
import { whatsappUrl } from "@/lib/login/support";

/** Numéro du support (configuration serveur), fourni une fois par la page. */
export const SupportNumber = createContext<string | null>(null);

export function SupportLink({
  message,
  label,
  variant = "secondary",
}: {
  message?: string;
  label?: string;
  variant?: "primary" | "secondary";
}) {
  const t = useTranslations("connexion.support");
  const href = whatsappUrl(useContext(SupportNumber), message ?? t("message"));
  if (!href) return null;
  return (
    <ButtonLink href={href} target="_blank" rel="noopener noreferrer" variant={variant}>
      <ChatIcon className="size-5" />
      {label ?? t("link")}
    </ButtonLink>
  );
}

export function LoginErrorAlert({ error, id }: { error: LoginError; id?: string | undefined }) {
  const t = useTranslations("connexion.errors");
  return (
    <Alert tone="error" id={id} action={error.support ? <SupportLink /> : undefined}>
      {t(error.key, error.values)}
    </Alert>
  );
}
