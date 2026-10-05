// Prix « à partir de » d'un service (spec 002, DESIGN.md › Mobile) : un seul montant, jamais une
// fourchette, toujours suivi de la mention de départ et de la phrase sur l'accord du client
// (règle de l'avenant, spec 004). Entier XOF (`formatXof`). Sans prix saisi : rien.
import { getTranslations } from "next-intl/server";

import { formatXof } from "@/lib/requests/format";

export async function PriceFrom({
  amount,
  className = "",
}: {
  /** Prix de départ en XOF entier, ou null s'il n'est pas saisi. */
  amount: number | null | undefined;
  className?: string;
}) {
  if (amount == null || !Number.isFinite(amount) || amount < 0) return null;
  const t = await getTranslations();
  return (
    <p className={className}>
      <span className="block font-display text-xl text-ink">
        {t("site.price.from", { amount: formatXof(amount) })}
      </span>
      <span className="block text-sm text-ink-muted">
        {t("catalog.priceNotice")} {t("site.price.agreement")}
      </span>
    </p>
  );
}
