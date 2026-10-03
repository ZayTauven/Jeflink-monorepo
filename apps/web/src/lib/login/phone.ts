// Saisie du numéro (spec 001, « Client, première connexion » et « Formats saisis »). L'API
// normalise elle-même (`77 123 45 67`, `771234567`, `00221…`, `221 77…`, `+221…`) : ici, on met
// seulement en forme pendant la frappe et on prépare une valeur sans ambiguïté d'indicatif.

/** Longueur du numéro national au Sénégal (`77 123 45 67`). */
const SN_NATIONAL_LENGTH = 9;

export function digitsOnly(value: string): string {
  return value.replace(/\D/g, "");
}

/**
 * Mise en forme pendant la frappe : `77 123 45 67` pour un numéro national sénégalais (groupes
 * 2-3-2-2), sinon les chiffres tels quels. Garde un `+` initial.
 */
export function formatPhoneInput(value: string): string {
  const plus = value.trimStart().startsWith("+") ? "+" : "";
  const digits = digitsOnly(value).slice(0, 15);
  if (plus || digits.length > SN_NATIONAL_LENGTH) return `${plus}${digits}`;
  const groups = [digits.slice(0, 2), digits.slice(2, 5), digits.slice(5, 7), digits.slice(7, 9)];
  return groups.filter(Boolean).join(" ");
}

/**
 * Valeur envoyée à l'API. Un numéro national reçoit l'indicatif choisi ; un numéro déjà
 * international (`+…`, `00…`, ou indicatif saisi) passe tel quel, au format `+chiffres`.
 */
export function phoneForApi(value: string, dialCode: string): string {
  const digits = digitsOnly(value);
  const dial = digitsOnly(dialCode);
  if (value.trimStart().startsWith("+")) return `+${digits}`;
  if (digits.startsWith("00")) return `+${digits.slice(2)}`;
  if (digits.length > SN_NATIONAL_LENGTH && digits.startsWith(dial)) return `+${digits}`;
  return `+${dial}${digits}`;
}

/** Assez de chiffres pour tenter l'envoi (l'API tranche ensuite). */
export function isPlausiblePhone(value: string): boolean {
  const length = digitsOnly(value).length;
  return length >= SN_NATIONAL_LENGTH && length <= 15;
}
