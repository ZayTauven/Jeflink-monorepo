// Message WhatsApp prérempli du site (spec 006). Il ne contient jamais de donnée personnelle :
// seulement le métier et le quartier de la page, plus des amorces à compléter par le client
// (« Problème : », « Mon repère : »). Le texte tapé dans « Votre quartier » n'y entre jamais.
// Les mots viennent de i18n ; ici, seulement l'assemblage. Module pur, testé seul.

export type WhatsappIntroKind = "both" | "trade" | "zone" | "none";

/** Quelle formule d'introduction choisir selon ce que la page sait. */
export function whatsappIntroKind(
  trade: string | null | undefined,
  where: string | null | undefined,
): WhatsappIntroKind {
  if (trade && where) return "both";
  if (trade) return "trade";
  if (where) return "zone";
  return "none";
}

/** Un libellé de catalogue sur une seule ligne : aucun saut de ligne ne vient des données. */
export function singleLine(text: string): string {
  return text.replace(/\s+/g, " ").trim();
}

/**
 * Introduction, ligne vide, puis une amorce par ligne. Les amorces restent ouvertes
 * (« Problème : ») : c'est le client qui les complète dans WhatsApp.
 */
export function composeWhatsappMessage(intro: string, primers: readonly string[]): string {
  const lines = primers.map(singleLine).filter(Boolean);
  const head = singleLine(intro);
  return lines.length ? `${head}\n\n${lines.join("\n")}` : head;
}
