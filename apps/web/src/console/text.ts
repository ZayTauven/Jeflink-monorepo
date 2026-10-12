/** Petits outils de texte de la console (français). */

/** « 1 pro à vérifier », « 3 pros à vérifier », « aucun… » au singulier. */
export function plural(n: number, one: string, many: string): string {
  return `${n.toLocaleString("fr-FR")} ${n > 1 ? many : one}`;
}

const rtf = new Intl.RelativeTimeFormat("fr", { numeric: "auto" });

/** « à l'instant », « il y a 3 heures », « hier »… */
export function ago(iso: string, now = Date.now()): string {
  const minutes = Math.round((new Date(iso).getTime() - now) / 60000);
  if (minutes > -1) return "à l'instant";
  if (minutes > -60) return rtf.format(minutes, "minute");
  if (minutes > -60 * 24) return rtf.format(Math.round(minutes / 60), "hour");
  return rtf.format(Math.round(minutes / 1440), "day");
}
