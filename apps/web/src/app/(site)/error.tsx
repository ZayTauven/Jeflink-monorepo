"use client";

// Erreur publique (spec 006, web 12). Question métier : « La page ne marche pas : que faire
// maintenant ? ». Réponse : réessayer, dire son quartier, écrire sur WhatsApp, revenir à l'accueil.
// Client Component sans composant serveur dedans : le cadre (en-tête, pied de page) vient du layout,
// les libellés des messages des îlots, le lien WhatsApp et les métiers du contexte du layout.
// Une panne de l'API n'est jamais une 404 : c'est cette page, avec le code 500.
import { useTranslations } from "next-intl";

import { RecoveryPanel } from "@/components/site/recovery-panel";
import { useSiteContext } from "@/components/site/site-context";
import { Button } from "@/components/ui/button";

export default function PublicError({ retry }: { error: Error; retry: () => void }) {
  const t = useTranslations("site.error");
  const tSearch = useTranslations("site.search");
  const tSite = useTranslations("site");
  const { supportHref, trades } = useSiteContext();
  return (
    <RecoveryPanel
      labels={{
        title: t("title"),
        lead: t("lead"),
        tradesTitle: t("tradesTitle"),
        whatsappLead: t("whatsappLead"),
        whatsapp: t("whatsapp"),
        newTab: tSite("newTab"),
        home: t("home"),
        search: {
          label: tSearch("label"),
          example: tSearch("example"),
          submit: tSearch("submit"),
        },
      }}
      trades={trades}
      supportHref={supportHref}
      action={
        <Button variant="primary" onClick={() => retry()}>
          {t("retry")}
        </Button>
      }
    />
  );
}
