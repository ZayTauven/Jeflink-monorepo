// En-tête du site public (Crafto section 1, adaptée) : logo, liens, « Mon espace » (toujours le
// même lien : une page publique ne lit jamais la session), pilule « Faire une demande ».
// Mobile : le bouton « Menu » (îlot client, voir MobileMenu).
import Link from "next/link";
import { getTranslations } from "next-intl/server";

import { buttonClass } from "@/components/ui/button";
import { Logo } from "@/components/ui/logo";
import { demandPath, SITE_PATHS } from "@/lib/site/paths";

import { MobileMenu } from "./mobile-menu";

const link =
  "inline-flex min-h-12 items-center rounded-pill px-4 text-base font-medium text-ink " +
  "hover:bg-sand focus-visible:outline-2 focus-visible:outline-offset-2 " +
  "focus-visible:outline-accent-strong";

export async function SiteHeader() {
  const t = await getTranslations("site.nav");
  const tBrand = await getTranslations("brand");
  const links = [
    { href: SITE_PATHS.trades, label: t("trades") },
    { href: SITE_PATHS.howItWorks, label: t("how") },
    { href: SITE_PATHS.about, label: t("about") },
    { href: SITE_PATHS.contact, label: t("contact") },
  ];
  const space = { href: SITE_PATHS.account, label: t("space") };
  const request = { href: demandPath(), label: t("request") };

  return (
    <header className="bg-paper">
      <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-4 py-3 sm:px-6">
        <Link
          href={SITE_PATHS.home}
          aria-label={tBrand("home")}
          className="inline-flex min-h-12 items-center"
        >
          <Logo />
        </Link>
        <nav aria-label={t("label")} className="hidden items-center gap-1 md:flex">
          {links.map((item) => (
            <Link key={item.href} href={item.href} className={link}>
              {item.label}
            </Link>
          ))}
        </nav>
        <div className="hidden items-center gap-2 md:flex">
          <Link href={space.href} className={link}>
            {space.label}
          </Link>
          <Link href={request.href} className={buttonClass("primary")}>
            {request.label}
          </Link>
        </div>
        <div className="md:hidden">
          <MobileMenu links={links} space={space} request={request} />
        </div>
      </div>
    </header>
  );
}
