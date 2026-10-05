// FAQ du site public : chaque réponse s'appuie sur une règle des specs 001 à 005 (`lib/site/faq-rules.ts`,
// vérifié par un test). Les délais viennent de `rules` ; sans `rules`, la variante sans chiffre.
// Le moment du paiement n'est pas dit (Q14) ; aucune promesse de délai ni de remboursement.
import { getTranslations } from "next-intl/server";

import { type FaqId } from "@/lib/site/faq-rules";

import { Faq, type FaqItem } from "./faq";
import type { Rules } from "./sections";

export async function SiteFaq({
  ids,
  rules,
  className = "",
}: {
  ids: readonly FaqId[];
  rules: Rules;
  className?: string;
}) {
  const t = await getTranslations("site.faq");
  const items: FaqItem[] = ids.map((id) => {
    const withRules = rules
      ? {
          hours: rules.pro_confirm_hours,
          urgent: rules.pro_confirm_hours_urgent,
        }
      : null;
    const hasVariant = id === "when" || id === "urgent" || id === "problem";
    let answer: string;
    if (id === "problem") {
      answer = rules
        ? t("items.problem.a", { hours: rules.dispute_window_hours })
        : t("items.problem.aNoRules");
    } else if (hasVariant) {
      answer = withRules ? t(`items.${id}.a`, withRules) : t(`items.${id}.aNoRules`);
    } else {
      answer = t(`items.${id}.a`);
    }
    return { id, question: t(`items.${id}.q`), answer };
  });
  return <Faq items={items} className={className} />;
}
