import type { NextRequest } from "next/server";

import { forbidden, sameOrigin } from "@/lib/actions";
import { api, getToken } from "@/lib/api";
import { jefReply } from "@/lib/jef";
import type { JefSession } from "@/lib/types";

/** Le client a répondu aux questions : Jef rédige la demande et la fiche du pro. */
export async function POST(req: NextRequest, ctx: { params: Promise<{ id: string }> }) {
  if (!sameOrigin(req)) return forbidden();
  const { id } = await ctx.params;
  if (!/^\d{1,9}$/.test(id)) return forbidden();
  const body = (await req.json().catch(() => ({}))) as { answers?: unknown };
  const answers: Record<string, string> = {};
  if (body.answers && typeof body.answers === "object") {
    for (const [key, value] of Object.entries(body.answers)) {
      if (/^q\d$/.test(key) && typeof value === "string") answers[key] = value.slice(0, 200);
    }
  }
  const res = await api<JefSession>(`/api/jef/${id}/brief/`, {
    method: "POST",
    token: await getToken(),
    body: { answers },
  });
  return jefReply(res);
}
