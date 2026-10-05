// Carte d'un métier (accueil, /metiers) : grande image arrondie (donnée par `icon_key`), pictogramme
// et libellé, description courte, le tout dans un seul lien. Image chargée à la demande.
import Link from "next/link";
import { getTranslations } from "next-intl/server";

import { tradePath } from "@/lib/site/paths";
import { tradeVisual } from "@/lib/site/visuals";

import { TradeLabel } from "./trade-label";
import { TradeVisual } from "./trade-visual";

export type TradeCardData = {
  slug: string;
  name: string;
  iconKey: string | null;
  description: string | null;
};

export async function TradeCard({ trade }: { trade: TradeCardData }) {
  const t = await getTranslations("site.trades");
  return (
    <Link
      href={tradePath(trade.slug)}
      className="group flex h-full flex-col gap-4 rounded-card border border-line bg-surface p-3 hover:border-ink focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-strong"
    >
      <TradeVisual iconKey={trade.iconKey} sizes="(min-width: 1024px) 360px, (min-width: 640px) 45vw, 100vw" />
      <div className="flex flex-1 flex-col gap-2 px-2 pb-3">
        {/* Photo : le libellé suffit. Visuel générique (pictogramme) : pictogramme et libellé. */}
        {tradeVisual(trade.iconKey).kind === "photo" ? (
          <span className="font-display text-2xl">{trade.name}</span>
        ) : (
          <TradeLabel iconKey={trade.iconKey} label={trade.name} className="font-display text-2xl" />
        )}
        {trade.description ? <p className="text-base text-ink-muted">{trade.description}</p> : null}
        <span className="mt-auto pt-2 text-base font-medium text-accent-strong underline underline-offset-4 group-hover:text-ink">
          {t("cardLink")}
        </span>
      </div>
    </Link>
  );
}
