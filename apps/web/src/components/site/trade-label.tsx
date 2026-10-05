// Pictogramme et libellé d'un métier (spec 002) : le pictogramme n'est jamais seul. Pastille
// `accent` et pictogramme `on-accent` (6,1:1), le libellé en texte `ink`.
import { TradeIcon } from "./trade-icon";

type Size = "sm" | "md";

const badge: Record<Size, string> = { sm: "size-8", md: "size-10" };

export function TradeLabel({
  iconKey,
  label,
  size = "md",
  className = "",
}: {
  /** `icon_key` du métier (donnée) ; null ou inconnu : pictogramme générique. */
  iconKey: string | null | undefined;
  label: string;
  size?: Size;
  className?: string;
}) {
  return (
    <span className={`inline-flex items-center gap-3 ${className}`}>
      <span
        className={`inline-flex shrink-0 items-center justify-center rounded-pill bg-accent text-on-accent ${badge[size]}`}
      >
        <TradeIcon iconKey={iconKey} className={size === "sm" ? "size-4" : "size-5"} />
      </span>
      <span className="font-medium">{label}</span>
    </span>
  );
}
