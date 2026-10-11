import type { NextRequest } from "next/server";

import { failure, forbidden, sameOrigin, success, text } from "@/lib/actions";
import { api, getToken } from "@/lib/api";

/** Actions sur une demande : devis (pro), choix du devis, fin de mission, annulation, avis. */
const BODIES: Record<string, (form: FormData) => unknown> = {
  quotes: (form) => ({
    amount: Number.parseInt(text(form, "amount").replace(/\D/g, ""), 10) || 0,
    message: text(form, "message"),
  }),
  accept: (form) => ({ quote_id: Number(text(form, "quote_id")) }),
  complete: () => ({}),
  cancel: () => ({}),
  review: (form) => ({ rating: Number(text(form, "rating")), comment: text(form, "comment") }),
};

export async function POST(
  req: NextRequest,
  ctx: { params: Promise<{ id: string; action: string }> },
) {
  if (!sameOrigin(req)) return forbidden();
  const { id, action } = await ctx.params;
  const body = BODIES[action];
  if (!/^\d+$/.test(id) || !body) return forbidden();
  const back = `/espace/demandes/${id}`;
  const res = await api(`/api/requests/${id}/${action}/`, {
    method: "POST",
    token: await getToken(),
    body: body(await req.formData()),
  });
  if (!res.ok) return failure(req, res, back);
  return success(req, back);
}
