import type { NextRequest } from "next/server";

import { failure, forbidden, sameOrigin, success } from "@/lib/actions";
import { api, getToken } from "@/lib/api";

const BACK = "/espace/profil#documents";

/** Retirer un de mes documents (à examiner ou refusé ; l'API refuse un document accepté). */
export async function POST(req: NextRequest, ctx: { params: Promise<{ id: string }> }) {
  if (!sameOrigin(req)) return forbidden();
  const { id } = await ctx.params;
  if (!/^\d{1,9}$/.test(id)) return success(req, BACK);
  const res = await api(`/api/auth/me/documents/${id}/`, {
    method: "DELETE",
    token: await getToken(),
  });
  if (!res.ok) return failure(req, res, BACK);
  return success(req, "/espace/profil?ok=document-retire#documents");
}
