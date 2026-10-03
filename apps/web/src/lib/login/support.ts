// Liens WhatsApp du support (spec 001, T3). Le message pré-rempli ne contient jamais de code ni
// de numéro complet ; le numéro du support vient de la configuration serveur.

/** Lien `wa.me` vers le support, ou null si le numéro n'est pas configuré. */
export function whatsappUrl(supportNumber: string | null, message: string): string | null {
  const digits = supportNumber?.replace(/\D/g, "") ?? "";
  if (digits.length < 8) return null;
  return `https://wa.me/${digits}?text=${encodeURIComponent(message)}`;
}
