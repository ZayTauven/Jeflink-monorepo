// Un gros chiffre (Crafto « 98 % », mais vrai : spec 006, Q5). Ne rend rien si le chiffre est
// absent : sous le seuil, l'API renvoie `null` et le site n'affiche ni « 0 » ni compteur vide.
import { getTranslations } from "next-intl/server";

import type { Figure } from "@/lib/site/figures";

export async function StatFigure({
  figure,
  className = "",
}: {
  figure: Figure | null | undefined;
  className?: string;
}) {
  if (!figure) return null;
  const t = await getTranslations("site.figures");
  let value: string;
  let label: string;
  switch (figure.kind) {
    case "quotes":
      value = t("quotes.value", { count: figure.value });
      label = t("quotes.label");
      break;
    case "dispute":
      value = t("dispute.value", { hours: figure.hours });
      label = t("dispute.label");
      break;
    case "fees":
      value = t("fees.value");
      label = t("fees.label");
      break;
    case "missions":
      value = t("missions.value", { count: figure.value });
      label = t("missions.label");
      break;
    case "pros":
      value = t(figure.value >= 10 ? "pros.approx" : "pros.exact", { count: figure.value });
      label = t("pros.label");
      break;
    case "rating":
      value = t("rating.value", { average: figure.average.toFixed(1).replace(".", ",") });
      label = t("rating.label", { count: figure.count });
      break;
  }
  return (
    <figure className={className}>
      <p className="font-display text-6xl leading-none tracking-tight text-ink">{value}</p>
      <figcaption className="mt-2 text-base text-ink-muted">{label}</figcaption>
    </figure>
  );
}
