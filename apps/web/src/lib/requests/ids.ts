// Identifiants et curseurs venus de l'URL : validés avant tout appel (spec 001, web 1).

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

export function isUuid(value: unknown): value is string {
  return typeof value === "string" && UUID.test(value);
}

/** Valeur du curseur de pagination dans l'URL `next` renvoyée par l'API, ou null. */
export function cursorFromNext(next: string | null | undefined): string | null {
  if (!next) return null;
  try {
    return new URL(next, "https://api.invalid").searchParams.get("cursor") || null;
  } catch {
    return null;
  }
}

/** Curseur reçu dans `?curseur=` : opaque, mais borné et sans caractère étranger. */
export function safeCursor(value: string | null | undefined): string | undefined {
  return value && value.length <= 200 && /^[A-Za-z0-9_=%.+/-]+$/.test(value) ? value : undefined;
}
