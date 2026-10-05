// Services d'un métier avec leur prix « à partir de » (un seul montant par service, jamais par
// métier : spec 002), suivis de la mention de départ et de la phrase sur l'accord du client.
// Chaque ligne mène à /demande pré-rempli avec le service. Sans prix saisi : « le prix est donné
// dans le devis ».
import Link from "next/link";
import { getTranslations } from "next-intl/server";

import { buttonClass } from "@/components/ui/button";
import { demandPath } from "@/lib/site/paths";

import { PriceFrom } from "./price-from";

export type ServiceRow = { slug: string; name: string; priceFromXof: number | null };

export async function ServicesList({
  tradeSlug,
  zoneSlug,
  services,
}: {
  tradeSlug: string;
  zoneSlug?: string | null;
  services: readonly ServiceRow[];
}) {
  const t = await getTranslations("site.trade");
  if (services.length === 0) return null;
  return (
    <ul className="border-t border-line">
      {services.map((service) => (
        <li
          key={service.slug}
          className="grid gap-3 border-b border-line py-5 sm:grid-cols-[1fr_1fr_auto] sm:items-center sm:gap-8"
        >
          <h3 className="font-display text-2xl tracking-tight">{service.name}</h3>
          {service.priceFromXof != null ? (
            <PriceFrom amount={service.priceFromXof} />
          ) : (
            <p className="text-base text-ink-muted">{t("noPrice")}</p>
          )}
          <Link
            href={demandPath({ metier: tradeSlug, quartier: zoneSlug, service: service.slug })}
            className={buttonClass("secondary")}
          >
            {t("requestService")}
          </Link>
        </li>
      ))}
    </ul>
  );
}
