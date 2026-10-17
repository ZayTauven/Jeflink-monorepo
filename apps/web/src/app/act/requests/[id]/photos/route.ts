import type { NextRequest } from "next/server";

import { failure, forbidden, sameOrigin, success } from "@/lib/actions";
import { api, getToken } from "@/lib/api";

const MAX_BODY = 9 * 1024 * 1024; // 8 Mo de photo côté API, plus l'enveloppe du formulaire

/** Ajouter une photo à ma demande (client, 3 au plus). */
export async function POST(req: NextRequest, ctx: { params: Promise<{ id: string }> }) {
  if (!sameOrigin(req)) return forbidden();
  const { id } = await ctx.params;
  if (!/^\d{1,9}$/.test(id)) return success(req, "/espace");
  const back = `/espace/demandes/${id}#photos`;
  const token = await getToken();
  if (!token) return success(req, `/connexion?suite=/espace/demandes/${id}`, null);
  if (Number(req.headers.get("content-length") ?? 0) > MAX_BODY) {
    const error = "Photo trop lourde : 8 Mo au plus.";
    return failure(req, { ok: false, status: 413, error, fields: {} }, back);
  }
  const photo = (await req.formData()).get("photo");
  if (!(photo instanceof File) || photo.size === 0) {
    return failure(
      req,
      { ok: false, status: 400, error: "Choisissez une photo.", fields: {} },
      back,
    );
  }
  const body = new FormData();
  body.append("photo", photo);
  const res = await api(`/api/requests/${id}/photos/`, { method: "POST", token, body });
  if (!res.ok)
    return failure(req, { ...res, error: res.fields.photo || res.error, fields: {} }, back);
  return success(req, `/espace/demandes/${id}?photo=ok#photos`);
}
