// Visuel d'un métier, choisi par `icon_key` (lib/site/visuals.ts) : photo de la banque, ou visuel
// générique (aplat `sand` et pictogramme) si le métier n'a pas de photo. `next/image` partout, avec
// `sizes` explicite : un téléphone ne télécharge jamais la variante de bureau. Chargement différé
// par défaut ; seule l'image LCP d'une page passe `eager`.
import Image from "next/image";
import { getTranslations } from "next-intl/server";

import { tradeVisual } from "@/lib/site/visuals";

import { TradeIcon } from "./trade-icon";

export async function TradeVisual({
  iconKey,
  variant = "card",
  sizes,
  eager = false,
  className = "",
}: {
  iconKey: string | null | undefined;
  /** `card` : carte (source 600 px) ; `compact` : page métier × quartier sur mobile (480 px). */
  variant?: "card" | "compact";
  /** Attribut `sizes` de l'image, par exemple « (min-width: 768px) 33vw, 100vw ». */
  sizes: string;
  eager?: boolean;
  className?: string;
}) {
  const visual = tradeVisual(iconKey);
  if (visual.kind === "generic") {
    return (
      <div
        aria-hidden="true"
        className={`flex aspect-[4/3] items-center justify-center rounded-card bg-sand text-accent-strong ${className}`}
      >
        <TradeIcon iconKey={iconKey} className="size-16" />
      </div>
    );
  }
  const t = await getTranslations("site.visuals");
  const file = variant === "compact" ? visual.compact : visual.card;
  return (
    <Image
      src={file.src}
      width={file.width}
      height={file.height}
      sizes={sizes}
      alt={t(visual.altKey)}
      loading={eager ? "eager" : "lazy"}
      className={`h-auto w-full rounded-card object-cover ${className}`}
    />
  );
}
