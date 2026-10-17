import type { NextRequest } from "next/server";

import { failure, forbidden, sameOrigin, success } from "@/lib/actions";
import { api, getToken } from "@/lib/api";

/** Retirer une photo de ma demande. */
export async function POST(
  req: NextRequest,
  ctx: { params: Promise<{ id: string; mid: string }> },
) {
  if (!sameOrigin(req)) return forbidden();
  const { id, mid } = await ctx.params;
  if (!/^\d{1,9}$/.test(id) || !/^\d{1,9}$/.test(mid)) return success(req, "/espace");
  const res = await api(`/api/requests/${id}/photos/${mid}/`, {
    method: "DELETE",
    token: await getToken(),
  });
  if (!res.ok) return failure(req, res, `/espace/demandes/${id}#photos`);
  return success(req, `/espace/demandes/${id}?photo=retiree#photos`);
}
