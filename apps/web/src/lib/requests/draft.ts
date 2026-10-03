// Brouillon de la demande (spec 003, web 1) : gardé dans le navigateur pour survivre à une
// coupure réseau ou à un onglet fermé. Jamais la position GPS ; périmé après 24 h (téléphone
// partagé, minimisation). Tout accès au stockage est protégé : bloqué, plein ou absent, le
// formulaire marche sans.

export const DRAFT_KEY = "jf-request-draft";
export const DRAFT_MAX_AGE_MS = 24 * 60 * 60 * 1000;

export type When = "asap" | "date";
export type Period = "morning" | "afternoon" | "evening" | "any";

export type Draft = {
  tradeSlug: string;
  serviceSlug: string;
  /** Slug du quartier choisi dans la liste ; vide si « autre quartier ». */
  zoneSlug: string;
  /** Quartier écrit à la main (« autre quartier »). */
  zoneText: string;
  otherZone: boolean;
  landmark: string;
  description: string;
  urgent: boolean;
  when: When;
  date: string;
  period: Period;
  /** Nom, demandé seulement si le profil est incomplet. */
  displayName: string;
  /** Clé d'idempotence de la tentative en cours (22 à 64 caractères). */
  idempotencyKey: string;
};

type StorageLike = Pick<Storage, "getItem" | "setItem" | "removeItem">;

export function emptyDraft(): Draft {
  return {
    tradeSlug: "",
    serviceSlug: "",
    zoneSlug: "",
    zoneText: "",
    otherZone: false,
    landmark: "",
    description: "",
    urgent: false,
    when: "asap",
    date: "",
    period: "any",
    displayName: "",
    idempotencyKey: "",
  };
}

const KEY_PATTERN = /^[A-Za-z0-9_-]{22,64}$/;

export function isIdempotencyKey(value: unknown): value is string {
  return typeof value === "string" && KEY_PATTERN.test(value);
}

/** Clé neuve : 32 caractères hexadécimaux issus d'un UUID. */
export function newIdempotencyKey(uuid: () => string = () => crypto.randomUUID()): string {
  return uuid().replaceAll("-", "");
}

function text(value: unknown, max: number): string {
  return typeof value === "string" ? value.slice(0, max) : "";
}

const WHENS: readonly string[] = ["asap", "date"];
const PERIODS: readonly string[] = ["morning", "afternoon", "evening", "any"];

/** Brouillon stocké, relu avec méfiance : tout champ inattendu est ignoré. */
export function parseDraft(raw: string | null, now: number = Date.now()): Draft | null {
  if (!raw) return null;
  let value: unknown;
  try {
    value = JSON.parse(raw);
  } catch {
    return null;
  }
  if (typeof value !== "object" || value === null) return null;
  const savedAt = (value as Record<string, unknown>).savedAt;
  if (typeof savedAt !== "number" || now - savedAt > DRAFT_MAX_AGE_MS || savedAt > now + 60_000) {
    return null;
  }
  return coerceDraft(value);
}

/** Champs d'un brouillon, relus avec méfiance : tout champ inattendu est ignoré. */
export function coerceDraft(value: unknown): Draft {
  const record =
    typeof value === "object" && value !== null ? (value as Record<string, unknown>) : {};
  const when =
    typeof record.when === "string" && WHENS.includes(record.when) ? record.when : "asap";
  const period =
    typeof record.period === "string" && PERIODS.includes(record.period) ? record.period : "any";
  const date = text(record.date, 10);
  return {
    tradeSlug: text(record.tradeSlug, 50),
    serviceSlug: text(record.serviceSlug, 50),
    zoneSlug: text(record.zoneSlug, 50),
    zoneText: text(record.zoneText, 80),
    otherZone: record.otherZone === true,
    landmark: text(record.landmark, 300),
    description: text(record.description, 1000),
    urgent: record.urgent === true,
    when: when as When,
    date: /^\d{4}-\d{2}-\d{2}$/.test(date) ? date : "",
    period: period as Period,
    displayName: text(record.displayName, 256),
    idempotencyKey: isIdempotencyKey(record.idempotencyKey) ? record.idempotencyKey : "",
  };
}

/** Texte à stocker : la position n'en fait jamais partie (elle n'existe pas dans `Draft`). */
export function serializeDraft(draft: Draft, now: number = Date.now()): string {
  return JSON.stringify({ ...draft, savedAt: now });
}

/** Brouillon vide : rien à garder. */
export function isBlank(draft: Draft): boolean {
  return (
    !draft.tradeSlug &&
    !draft.serviceSlug &&
    !draft.zoneSlug &&
    !draft.zoneText.trim() &&
    !draft.landmark.trim() &&
    !draft.description.trim() &&
    !draft.displayName.trim()
  );
}

export function browserStorage(): StorageLike | undefined {
  try {
    return window.localStorage;
  } catch {
    return undefined;
  }
}

export function loadDraft(
  storage: StorageLike | undefined,
  now: number = Date.now(),
): Draft | null {
  if (!storage) return null;
  try {
    const draft = parseDraft(storage.getItem(DRAFT_KEY), now);
    if (!draft) storage.removeItem(DRAFT_KEY); // périmé ou illisible : on ne le garde pas
    return draft;
  } catch {
    return null;
  }
}

export function saveDraft(
  storage: StorageLike | undefined,
  draft: Draft,
  now: number = Date.now(),
): void {
  if (!storage) return;
  try {
    if (isBlank(draft)) storage.removeItem(DRAFT_KEY);
    else storage.setItem(DRAFT_KEY, serializeDraft(draft, now));
  } catch {
    // stockage plein ou bloqué : le formulaire marche sans brouillon
  }
}

export function clearDraft(storage: StorageLike | undefined): void {
  if (!storage) return;
  try {
    storage.removeItem(DRAFT_KEY);
  } catch {
    // rien à faire
  }
}
