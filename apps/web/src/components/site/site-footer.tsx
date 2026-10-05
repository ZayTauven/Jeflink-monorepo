// Pied de page du site public (Crafto section 13, adaptée) : fond `ink`. Il porte tous les liens
// du site (suffisants sans JS : le bouton « Menu » y mène), le numéro du support en clair avec ses
// horaires, et le nom de la société, contre l'usurpation (spec 006). « Dakar » sans adresse
// inventée ; pas de réseaux sociaux ni de pages légales tant qu'ils n'existent pas.
import Link from "next/link";
import { getTranslations } from "next-intl/server";

import { CallIcon, ChatIcon } from "@/components/ui/icons";
import { LogoMark } from "@/components/ui/logo";
import { whatsappUrl } from "@/lib/login/support";
import { formatPhoneDisplay } from "@/lib/requests/format";
import { SITE_PATHS, tradePath } from "@/lib/site/paths";
import { readSiteConfig } from "@/lib/site-config";

export type FooterTrade = { slug: string; name: string };

const link =
  "inline-flex min-h-12 items-center text-base text-paper underline-offset-4 hover:underline " +
  "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent";

const title = "font-display text-xl text-paper";

export async function SiteFooter({ trades = [] }: { trades?: readonly FooterTrade[] }) {
  const t = await getTranslations("site");
  const { supportWhatsapp, supportPhone, legalName } = readSiteConfig(process.env);
  const whatsapp = whatsappUrl(supportWhatsapp, t("footer.supportMessage"));
  const pages = [
    { href: SITE_PATHS.trades, label: t("nav.trades") },
    { href: SITE_PATHS.howItWorks, label: t("nav.how") },
    { href: SITE_PATHS.about, label: t("nav.about") },
    { href: SITE_PATHS.contact, label: t("nav.contact") },
    { href: SITE_PATHS.becomePro, label: t("nav.pro") },
    { href: SITE_PATHS.account, label: t("nav.space") },
  ];

  return (
    <footer id="pied-de-page" aria-label={t("footer.label")} className="bg-ink text-sand">
      <div className="mx-auto max-w-6xl px-4 py-12 sm:px-6 sm:py-16">
        <div className={`grid gap-10 ${trades.length > 0 ? "md:grid-cols-3" : "md:grid-cols-2"}`}>
          <section aria-labelledby="pied-support">
            <h2 id="pied-support" className={title}>
              {t("footer.supportTitle")}
            </h2>
            <ul className="mt-3 flex flex-col">
              {whatsapp && supportWhatsapp ? (
                <li>
                  <a href={whatsapp} target="_blank" rel="noopener noreferrer" className={link}>
                    <ChatIcon className="mr-2 size-5 shrink-0" />
                    <span>
                      {t("footer.whatsapp")}
                      <span className="block text-sm text-sand">
                        {formatPhoneDisplay(`+${supportWhatsapp}`)}
                      </span>
                    </span>
                  </a>
                </li>
              ) : null}
              {supportPhone ? (
                <li>
                  <a href={`tel:${supportPhone}`} className={link}>
                    <CallIcon className="mr-2 size-5 shrink-0" />
                    <span>
                      {t("footer.call")}
                      <span className="block text-sm text-sand">
                        {formatPhoneDisplay(supportPhone)}
                      </span>
                    </span>
                  </a>
                </li>
              ) : null}
            </ul>
            <p className="mt-3 text-base">{t("footer.hours")}</p>
            <p className="mt-1 text-base">{t("footer.onlyNumbers")}</p>
          </section>

          <nav aria-labelledby="pied-pages">
            <h2 id="pied-pages" className={title}>
              {t("footer.pagesTitle")}
            </h2>
            <ul className="mt-3 flex flex-col">
              {pages.map((item) => (
                <li key={item.href}>
                  <Link href={item.href} className={link}>
                    {item.label}
                  </Link>
                </li>
              ))}
            </ul>
          </nav>

          {trades.length > 0 ? (
            <nav aria-labelledby="pied-metiers">
              <h2 id="pied-metiers" className={title}>
                {t("footer.tradesTitle")}
              </h2>
              <ul className="mt-3 flex flex-col">
                {trades.map((trade) => (
                  <li key={trade.slug}>
                    <Link href={tradePath(trade.slug)} className={link}>
                      {trade.name}
                    </Link>
                  </li>
                ))}
              </ul>
            </nav>
          ) : null}
        </div>

        <div className="mt-12 flex flex-col gap-6 border-t border-sand/30 pt-8 sm:flex-row sm:items-end sm:justify-between">
          <div className="text-base">
            <p>{t("footer.city")}</p>
            {legalName ? <p className="mt-1">{t("footer.legal", { name: legalName })}</p> : null}
          </div>
          <LogoMark tone="onDark" className="h-20 w-auto sm:h-28" />
        </div>
      </div>
    </footer>
  );
}
