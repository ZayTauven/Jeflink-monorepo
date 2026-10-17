import type { NextRequest } from "next/server";

import { failure, forbidden, sameOrigin, success, text } from "@/lib/actions";
import { api, getToken } from "@/lib/api";

const BACK = "/espace";

/** Ma photo de profil : « photo » (fichier) la remplace, « remove=1 » la retire. */
export async function POST(req: NextRequest) {
  if (!sameOrigin(req)) return forbidden();
  const form = await req.formData();
  const token = await getToken();
  if (text(form, "remove") === "1") {
    const res = await api("/api/auth/me/photo/", { method: "DELETE", token });
    if (!res.ok) return failure(req, res, BACK);
    return success(req, `${BACK}?photo=retiree`);
  }
  const photo = form.get("photo");
  if (!(photo instanceof File) || photo.size === 0) {
    return failure(
      req,
      { ok: false, status: 400, error: "Choisissez une photo.", fields: {} },
      BACK,
    );
  }
  const body = new FormData();
  body.append("photo", photo);
  const res = await api("/api/auth/me/photo/", { method: "POST", token, body });
  // Un seul champ : son message suffit (pas de « Vérifiez le formulaire » en plus).
  if (!res.ok)
    return failure(req, { ...res, error: res.fields.photo || res.error, fields: {} }, BACK);
  return success(req, `${BACK}?photo=ok`);
}
