// FAQ du site public : chaque réponse s'appuie sur une règle des specs 001 à 005, citée ici à côté
// de sa clé (`site.faq.items.<id>`). Un test vérifie que chaque question affichée a sa règle et
// que chaque clé de `fr.json` est connue. Le moment du paiement n'est pas dit (Q14).
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

/** FAQ de l'accueil, dans l'ordre d'affichage. */
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
