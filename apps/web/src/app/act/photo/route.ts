import type { NextRequest } from "next/server";

import { failure, forbidden, sameOrigin, success, text } from "@/lib/actions";
import { api, getToken } from "@/lib/api";

const BACK = "/espace";
const MAX_BODY = 9 * 1024 * 1024; // 8 Mo d'image côté API, plus l'enveloppe du formulaire

/** Ma photo de profil : « photo » (fichier) la remplace, « remove=1 » la retire. */
export async function POST(req: NextRequest) {
  if (!sameOrigin(req)) return forbidden();
  // Jeton et taille vérifiés avant de lire le corps (un anonyme ne fait rien charger).
  const token = await getToken();
  if (!token) return success(req, `/connexion?suite=${BACK}`, null);
  if (Number(req.headers.get("content-length") ?? 0) > MAX_BODY) {
    const error = "Image trop lourde : 8 Mo au plus.";
    return failure(req, { ok: false, status: 413, error, fields: {} }, BACK);
  }
  const form = await req.formData();
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
