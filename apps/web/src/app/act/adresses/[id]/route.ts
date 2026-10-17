import type { NextRequest } from "next/server";

import { failure, forbidden, sameOrigin, success } from "@/lib/actions";
import { api, getToken } from "@/lib/api";

const BACK = "/espace/profil#adresses";

/** Supprimer une de mes adresses (l'API ne trouve que les miennes). */
export async function POST(req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  if (!sameOrigin(req)) return forbidden();
  const { id } = await params;
  if (!/^\d{1,9}$/.test(id)) return success(req, BACK);
  const res = await api(`/api/auth/me/addresses/${id}/`, {
    method: "DELETE",
    token: await getToken(),
  });
  if (!res.ok) return failure(req, res, BACK);
  return success(req, "/espace/profil?ok=adresse-retiree#adresses");
}
