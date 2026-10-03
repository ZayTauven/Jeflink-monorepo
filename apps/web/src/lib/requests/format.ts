// Formats d'affichage des demandes et devis (spec 003, web 2). Modules purs, testés seuls.
// Montants : entiers XOF, jamais de décimales. Heures : toujours `Africa/Dakar`.

export const DAKAR_TZ = "Africa/Dakar";

/**
 * « 25 000 F CFA ». L'espace est U+00A0 : Funnel Display n'a pas l'espace fine insécable U+202F
 * que `Intl` insère (DESIGN.md › Typographie).
 */
export function formatXof(amount: number): string {
  const whole = Math.trunc(Number.isFinite(amount) ? amount : 0);
  const sign = whole < 0 ? "-" : "";
  const digits = String(Math.abs(whole)).replace(/\B(?=(\d{3})+(?!\d))/g, " ");
  return `${sign}${digits} F CFA`;
}

type DakarParts = {
  year: number;
  month: number;
  day: number;
  hour: number;
  minute: number;
};

const partsFormat = new Intl.DateTimeFormat("en-US", {
  timeZone: DAKAR_TZ,
  year: "numeric",
  month: "numeric",
  day: "numeric",
  hour: "numeric",
  minute: "numeric",
  hourCycle: "h23",
});

/** Date et heure murales à Dakar d'un instant ISO (UTC), ou null si la date est invalide. */
export function dakarParts(iso: string | Date): DakarParts | null {
  const date = iso instanceof Date ? iso : new Date(iso);
  if (Number.isNaN(date.getTime())) return null;
  const parts: Record<string, number> = {};
  for (const part of partsFormat.formatToParts(date)) {
    if (part.type !== "literal") parts[part.type] = Number(part.value);
  }
  return {
    year: parts.year ?? 0,
    month: parts.month ?? 0,
    day: parts.day ?? 0,
    hour: parts.hour ?? 0,
    minute: parts.minute ?? 0,
  };
}

/** « 14 h 30 », ou « 14 h » pile. Chaîne vide si la date est invalide. */
export function formatClock(iso: string | Date): string {
  const p = dakarParts(iso);
  if (!p) return "";
  return p.minute === 0 ? `${p.hour} h` : `${p.hour} h ${String(p.minute).padStart(2, "0")}`;
}

/** Numéro de jour civil à Dakar (pour compter des jours d'écart sans effet d'heure). */
function dayNumber(p: DakarParts): number {
  return Math.floor(Date.UTC(p.year, p.month - 1, p.day) / 86_400_000);
}

export type SlotPeriod = "morning" | "afternoon" | "evening";
export type SlotDay =
  | { kind: "today" }
  | { kind: "tomorrow" }
  | { kind: "weekday"; text: string }
  | { kind: "date"; text: string };

export type SlotLabel = {
  day: SlotDay;
  period: SlotPeriod;
  /** « 8 h » */
  from: string;
  /** « 12 h » */
  to: string;
};

/** Plages de l'API (`SLOT_PERIODS`) : matin avant 12 h, après-midi avant 17 h, soir ensuite. */
export function periodOf(hour: number): SlotPeriod {
  if (hour < 12) return "morning";
  if (hour < 17) return "afternoon";
  return "evening";
}

function capitalize(text: string): string {
  return text.charAt(0).toUpperCase() + text.slice(1);
}

/**
 * Créneau en langage courant : jour (aujourd'hui, demain, jour de la semaine, date) et plage
 * (matin, après-midi, soir), calculés en heure de Dakar. Les mots eux-mêmes viennent de i18n ;
 * ici seuls les noms de jour et de mois sortent d'`Intl`.
 */
export function slotLabel(
  startIso: string,
  endIso: string,
  now: string | Date = new Date(),
  locale = "fr",
): SlotLabel | null {
  const start = dakarParts(startIso);
  const end = dakarParts(endIso);
  const today = dakarParts(now);
  if (!start || !end || !today) return null;
  const diff = dayNumber(start) - dayNumber(today);
  let day: SlotDay;
  if (diff === 0) day = { kind: "today" };
  else if (diff === 1) day = { kind: "tomorrow" };
  else if (diff > 1 && diff < 7) {
    day = {
      kind: "weekday",
      text: capitalize(
        new Intl.DateTimeFormat(locale, { timeZone: DAKAR_TZ, weekday: "long" }).format(
          new Date(startIso),
        ),
      ),
    };
  } else {
    day = {
      kind: "date",
      text: new Intl.DateTimeFormat(locale, {
        timeZone: DAKAR_TZ,
        day: "numeric",
        month: "short",
      }).format(new Date(startIso)),
    };
  }
  return {
    day,
    period: periodOf(start.hour),
    from: formatClock(startIso),
    to: formatClock(endIso),
  };
}

/** « 12 oct. · 14 h 30 » (DESIGN.md). */
export function formatDateTime(iso: string | Date, locale = "fr"): string {
  const date = iso instanceof Date ? iso : new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  const day = new Intl.DateTimeFormat(locale, {
    timeZone: DAKAR_TZ,
    day: "numeric",
    month: "short",
  }).format(date);
  return `${day} · ${formatClock(date)}`;
}

/** « 12 oct. » */
export function formatDay(iso: string | Date, locale = "fr"): string {
  const date = iso instanceof Date ? iso : new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return new Intl.DateTimeFormat(locale, {
    timeZone: DAKAR_TZ,
    day: "numeric",
    month: "short",
  }).format(date);
}

/** Aujourd'hui à Dakar, au format `AAAA-MM-JJ` (champ date du formulaire). */
export function dakarToday(now: string | Date = new Date()): string {
  const p = dakarParts(now);
  if (!p) return "";
  return `${p.year}-${String(p.month).padStart(2, "0")}-${String(p.day).padStart(2, "0")}`;
}

/** « +221 77 123 45 67 » pour un numéro sénégalais E.164 ; tout autre numéro reste tel quel. */
export function formatPhoneDisplay(e164: string): string {
  const match = /^\+221(\d{2})(\d{3})(\d{2})(\d{2})$/.exec(e164);
  if (!match) return e164;
  return `+221 ${match[1]} ${match[2]} ${match[3]} ${match[4]}`;
}

/** Numéro E.164 plausible : décide d'un lien `tel:` ou `wa.me`. */
export function isE164(value: string): boolean {
  return /^\+[1-9]\d{7,14}$/.test(value);
}
