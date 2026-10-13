import type { NextRequest } from "next/server";

import { forbidden, sameOrigin } from "@/lib/actions";
import { api, getToken } from "@/lib/api";
import { jefReply } from "@/lib/jef";
import type { JefSession } from "@/lib/types";

/** Le client décrit son souci : Jef propose un métier et pose ses questions. */
export async function POST(req: NextRequest) {
  if (!sameOrigin(req)) return forbidden();
  const body = (await req.json().catch(() => ({}))) as { text?: unknown; trade?: unknown };
  const res = await api<JefSession>("/api/jef/", {
    method: "POST",
    token: await getToken(),
    body: {
      text: typeof body.text === "string" ? body.text.slice(0, 2000) : "",
      trade: typeof body.trade === "string" ? body.trade.slice(0, 40) : "",
    },
  });
  return jefReply(res);
}
