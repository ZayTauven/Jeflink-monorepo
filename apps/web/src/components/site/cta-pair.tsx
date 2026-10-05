// CTA double du site (CLAUDE.md d'apps/web) : « Faire une demande » et « Écrire sur WhatsApp »,
// au même rang. La demande mène à /demande pré-rempli ; WhatsApp ouvre un message prérempli avec
// le métier et le quartier de la page et des amorces à compléter, sans aucune donnée personnelle.
// Sans numéro configuré, le bouton WhatsApp n'apparaît pas. Variante `bar` : sans mention, pour la
// barre d'actions fixe du mobile.
import Link from "next/link";
import { getTranslations } from "next-intl/server";

import { SupportLink } from "@/components/support-link";
import { buttonClass } from "@/components/ui/button";
import { demandPath } from "@/lib/site/paths";
import { readSiteConfig } from "@/lib/site-config";
import { zoneLocative } from "@/lib/site/locative";
import {
  composeWhatsappMessage,
  singleLine,
  whatsappIntroKind,
} from "@/lib/site/whatsapp";

export type CtaContext = {
  /** Métier de la page ; `name` en minuscules ou casse du catalogue, tel qu'affiché. */
  trade?: { slug: string; name: string } | null;
  /** Quartier de la page ; `locative` saisi par l'Ops (« aux Almadies »), repli « à {nom} ». */
  zone?: { slug: string; name: string; locative?: { fr: string; wo: string | null } | null } | null;
  /** Service précis (ligne de service) : ajouté au lien de demande. */
  serviceSlug?: string | null;
};

export type CtaPairProps = CtaContext & {
  variant?: "hero" | "bar";
  /** Ajoute « Je préfère en wolof » (seulement avec une formule validée par un locuteur, Q2). */
  wolof?: boolean;
  /** Ajoute le lien « C'est urgent ? » vers la demande urgente. */
  urgentLink?: boolean;
  /** `id` de la mention SMS, reliée au bouton de demande (un seul CtaPair `hero` par page). */
  noticeId?: string;
  className?: string;
};

export async function CtaPair({
  trade,
  zone,
  serviceSlug,
  variant = "hero",
  wolof = false,
  urgentLink = false,
  noticeId = "cta-notice",
  className = "",
}: CtaPairProps) {
  const t = await getTranslations("site");
  const { supportWhatsapp } = readSiteConfig(process.env);
  const bar = variant === "bar";

  const where = zone ? zoneLocative(zone, (name) => t("seo.locativeFallback", { name })) : "";
  const tradeName = trade ? singleLine(trade.name) : "";
  const primers = [t("whatsapp.primerProblem"), t("whatsapp.primerPlace")];
  const message = composeWhatsappMessage(
    t("whatsapp.intro", {
      kind: whatsappIntroKind(tradeName, where),
      trade: tradeName,
      where: singleLine(where),
    }),
    primers,
  );
  const wolofMessage = composeWhatsappMessage(t("whatsapp.introWolof"), primers);

  const demandBase = { metier: trade?.slug, quartier: zone?.slug, service: serviceSlug };
  const grow = bar ? "px-4!" : "";

  return (
    <div className={className}>
      <div className={bar ? "flex gap-2" : "flex flex-col gap-3 sm:flex-row"}>
        <Link
          href={demandPath(demandBase)}
          aria-describedby={bar ? undefined : noticeId}
          className={buttonClass("primary", bar ? `flex-[3] ${grow}` : "")}
        >
          {t("cta.request")}
        </Link>
        <SupportLink
          number={supportWhatsapp}
          message={message}
          label={bar ? t("cta.whatsappShort") : t("cta.whatsapp")}
          className={bar ? `flex-[2] ${grow}` : ""}
        />
      </div>
      {bar ? null : (
        <p id={noticeId} className="mt-3 text-sm text-ink-muted">
          {t("cta.smsNotice")}
        </p>
      )}
      {bar ? null : (
        <div className="mt-1 flex flex-wrap gap-x-4">
          {urgentLink ? (
            <Link
              href={demandPath({ ...demandBase, urgence: true })}
              className={buttonClass("quiet", "px-0!")}
            >
              {t("cta.urgent")}
            </Link>
          ) : null}
          {wolof ? (
            <SupportLink
              number={supportWhatsapp}
              message={wolofMessage}
              label={t("cta.wolof")}
              variant="quiet"
            />
          ) : null}
        </div>
      )}
    </div>
  );
}
