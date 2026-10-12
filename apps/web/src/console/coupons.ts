/** Affichage d'un code promo dans la console (valeur, état, conditions). */
import { formatXOF } from "@/lib/format";

import type { CouponAdmin, CouponState } from "./types";

const NBSP = " ";

export const COUPON_STATE: Record<CouponState, { label: string; cls: string }> = {
  active: { label: "En cours", cls: "jf-status--done" },
  scheduled: { label: "Programmé", cls: "jf-status--booked" },
  expired: { label: "Expiré", cls: "jf-status--cancelled" },
  exhausted: { label: "Épuisé", cls: "jf-status--open" },
  off: { label: "Désactivé", cls: "jf-status--cancelled" },
};

/** « −20 % (max 3 000 F CFA) » ou « −2 000 F CFA ». */
export function couponValue(c: CouponAdmin): string {
  if (c.kind === "fixed") return `−${formatXOF(c.value)}`;
  return `−${c.value}${NBSP}%${c.max_discount ? ` (max ${formatXOF(c.max_discount)})` : ""}`;
}

export function couponRules(c: CouponAdmin): string[] {
  const rules: string[] = [];
  if (c.min_amount) rules.push(`devis dès ${formatXOF(c.min_amount)}`);
  if (c.first_order_only) rules.push("première commande");
  if (c.trades.length) rules.push(c.trades.map((t) => t.name).join(", "));
  if (c.zones.length) rules.push(c.zones.map((z) => z.name).join(", "));
  rules.push(
    c.max_uses_per_client > 1 ? `${c.max_uses_per_client} fois par client` : "1 fois par client",
  );
  return rules;
}
