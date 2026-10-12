/** Argent dans la console : libellés des soldes des pros. */
import { formatXOF } from "@/lib/format";

/** « Doit 25 040 F CFA à Jeflink » / « Jeflink lui doit 2 000 F CFA » / « À jour ». */
export function balanceLabel(balance: number): { text: string; cls: string } {
  if (balance > 0) return { text: `Doit ${formatXOF(balance)}`, cls: "jf-status--open" };
  if (balance < 0)
    return { text: `Jeflink lui doit ${formatXOF(-balance)}`, cls: "jf-status--booked" };
  return { text: "À jour", cls: "jf-status--done" };
}
