// /demande (spec 003, web 1). Question métier : « Comment décrire mon besoin pour recevoir des
// devis ? ». Action principale : « Envoyer ma demande ».
//
// Session exigée : sans session, l'appel de profil répond 401 et `rethrowApiError` renvoie à
// `/connexion?next=/demande` (ou au rebond de refresh). Le catalogue arrive avec la page : un seul
// aller-retour sur un réseau lent, puis la recherche se fait hors ligne dans le navigateur.
import {
  type TradeDetail,
  type Zone,
  catalogTradeRetrieve,
  catalogTradesList,
  meRetrieve,
  zonesList,
} from "@jeflink/api-client";
import type { Metadata } from "next";
import { getLocale, getTranslations } from "next-intl/server";

import { PageShell } from "@/components/page-shell";
import { Alert } from "@/components/ui/alert";
import { ButtonLink } from "@/components/ui/button";
import { rethrowApiError, serverApiWithSession } from "@/lib/bff";
import { toTradeOptions, toZoneOptions } from "@/lib/requests/catalog";
import { readSiteConfig } from "@/lib/site-config";

import { RequestForm } from "./_components/request-form";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("requests.form");
  return { title: t("metaTitle"), robots: { index: false, follow: false } };
}

export default async function RequestPage() {
  const api = await serverApiWithSession();
  const t = await getTranslations("requests.form");
  const locale = await getLocale();

  let profileComplete = true;
  try {
    const me = await meRetrieve(api.options);
    profileComplete = me.data.profile_status === "complete";
  } catch (error) {
    return rethrowApiError(error, api);
  }

  let trades: TradeDetail[] = [];
  let zones: Zone[] = [];
  let failed = false;
  try {
    const [tradeList, zoneList] = await Promise.all([
      catalogTradesList(api.options),
      zonesList(undefined, api.options),
    ]);
    zones = zoneList.data;
    // Services de chaque métier : quelques petits appels internes, en parallèle (6 métiers au
    // lancement). Au-delà d'une vingtaine de métiers, passer à un chargement à la demande.
    trades = (
      await Promise.all(
        tradeList.data.map((trade) => catalogTradeRetrieve(trade.slug, api.options)),
      )
    ).flatMap((response) => (response.status === 200 ? [response.data] : []));
  } catch {
    failed = true;
  }

  const { supportWhatsapp } = readSiteConfig(process.env);

  return (
    <PageShell>
      <header className="mb-8 flex flex-col gap-3">
        <h1 className="font-display text-balance text-4xl leading-[1.05] tracking-tight sm:text-5xl">
          {t("title")}
        </h1>
        <p className="text-lg leading-relaxed text-ink-muted">{t("lead")}</p>
      </header>
      {failed || trades.length === 0 || zones.length === 0 ? (
        <Alert
          tone="error"
          action={
            <ButtonLink href="/demande" variant="secondary" className="self-start">
              {t("reload")}
            </ButtonLink>
          }
        >
          {t("unavailable")}
        </Alert>
      ) : (
        <RequestForm
          trades={toTradeOptions(trades, locale)}
          zones={toZoneOptions(zones)}
          profileComplete={profileComplete}
          supportWhatsapp={supportWhatsapp}
        />
      )}
    </PageShell>
  );
}
