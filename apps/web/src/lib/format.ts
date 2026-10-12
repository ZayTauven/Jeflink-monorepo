// Montants : entiers en F CFA. Dates : stockées en UTC, affichées à l'heure de Dakar.

const xof = new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 0 });

export function formatXOF(amount: number): string {
  // Vrai signe moins (U+2212) et espaces insécables : « −400 F CFA » ne se coupe jamais.
  return `${xof.format(amount).replace("-", "−")} F CFA`;
}

export function formatDate(iso: string, withTime = false): string {
  return new Intl.DateTimeFormat("fr-FR", {
    timeZone: "Africa/Dakar",
    day: "numeric",
    month: "long",
    year: "numeric",
    ...(withTime ? { hour: "2-digit", minute: "2-digit" } : {}),
  }).format(new Date(iso));
}

export function formatRating(average: number | null): string {
  return average === null ? "—" : average.toLocaleString("fr-FR", { minimumFractionDigits: 1 });
}
