// FAQ du site public : chaque réponse s'appuie sur une règle des specs 001 à 005 (champ `rule`,
// vérifié par un test). Les délais viennent de `rules` ; sans `rules`, la variante sans chiffre.
// Le moment du paiement n'est pas dit (Q14) ; aucune promesse de délai ni de remboursement.
import { getTranslations } from "next-intl/server";

import { Faq, type FaqItem } from "./faq";
import type { Rules } from "./sections";

export const FAQ_RULES = {
  cost: "specs 002, 003, 004 : prix de départ, devis choisi, avenant refusé = prix accepté",
  pay: "specs 003, 005 : règlement direct, aucun frais client ; moment du paiement : Q14",
  when: "spec 003 : créneau dans le devis, confirmation du pro sous pro_confirm_hours",
  urgent: "spec 003 : case « C'est urgent », confirmation sous pro_confirm_hours_urgent",
  zone: "specs 002, 003 : « Autre quartier » et WhatsApp",
  noshow: "spec 004 : « Le pro n'est pas venu », la demande revient vers les pros",
  problem: "spec 004 : dispute_window_hours pour signaler, Jeflink examine",
  genuine: "spec 001 : le SMS dit de ne donner le code à personne ; spec 004 : code de fin",
  relative: "spec 004 : repère du proche, partage du code de fin par WhatsApp",
  abroad: "spec 001, Q1 : connexion réservée aux numéros du Sénégal en V1",
  wolof: "Q8 : le support répond en wolof sur WhatsApp",
  verified: "Q7 : procédure « Pro vérifié » (docs/ops), liste réelle seulement",
} as const;

export type FaqId = keyof typeof FAQ_RULES;

export const FULL_FAQ: readonly FaqId[] = [
  "cost",
  "pay",
  "when",
  "urgent",
  "zone",
  "noshow",
  "problem",
  "genuine",
  "relative",
  "abroad",
  "wolof",
  "verified",
];

/** Questions courtes des pages métier et métier × quartier. */
export const SHORT_FAQ: readonly FaqId[] = ["cost", "pay", "when", "urgent", "genuine"];

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
