// Devis à comparer (spec 003, web 2). Tri par créneau, jamais par prix : pas de course au
// moins-disant. Le serveur trie déjà ; on garde l'ordre ici aussi, pour ne rien devoir à lui.
import type { ClientQuote } from "@jeflink/api-client";

/** Du créneau le plus proche au plus lointain ; à égalité, la fin du créneau, puis l'identifiant. */
export function sortQuotes<T extends Pick<ClientQuote, "slot_start" | "slot_end" | "public_id">>(
  quotes: readonly T[],
): T[] {
  const time = (iso: string): number => {
    const value = Date.parse(iso);
    return Number.isNaN(value) ? Number.MAX_SAFE_INTEGER : value;
  };
  return [...quotes].sort(
    (a, b) =>
      time(a.slot_start) - time(b.slot_start) ||
      time(a.slot_end) - time(b.slot_end) ||
      a.public_id.localeCompare(b.public_id),
  );
}

/** Devis qu'un client peut encore choisir : ceux en lice. */
export function choosableQuotes<T extends Pick<ClientQuote, "status">>(quotes: readonly T[]): T[] {
  return quotes.filter((quote) => quote.status === "submitted" || quote.status === "held");
}

/** Libellé de ligne masqué par l'API avant la confirmation (« •••••••• ») : rien à afficher. */
export function readableLabel(label: string): string {
  const text = label.trim();
  return /^[•·*\s]*$/.test(text) ? "" : text;
}
