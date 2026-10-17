import type { NextRequest } from "next/server";

import { failure, forbidden, sameOrigin, success, text } from "@/lib/actions";
import { api, getToken } from "@/lib/api";

const BACK = "/espace/profil#documents";
const MAX_BODY = 9 * 1024 * 1024; // 8 Mo de fichier côté API, plus l'enveloppe du formulaire

/** Envoyer un justificatif (pro) : photo ou PDF, examiné par l'équipe. */
export async function POST(req: NextRequest) {
  if (!sameOrigin(req)) return forbidden();
  const token = await getToken();
  if (!token) return success(req, "/connexion?suite=/espace/profil", null);
  if (Number(req.headers.get("content-length") ?? 0) > MAX_BODY) {
    const error = "Fichier trop lourd : 8 Mo au plus.";
    return failure(req, { ok: false, status: 413, error, fields: {} }, BACK);
  }
  const form = await req.formData();
  const file = form.get("file");
  if (!(file instanceof File) || file.size === 0) {
    const error = "Choisissez une photo ou un PDF.";
    return failure(req, { ok: false, status: 400, error, fields: {} }, BACK);
  }
  const body = new FormData();
  body.append("kind", text(form, "kind"));
  body.append("file", file);
  const res = await api("/api/auth/me/documents/", { method: "POST", token, body });
  if (!res.ok) {
    const error = res.fields.file || res.fields.kind || res.error;
    return failure(req, { ...res, error, fields: {} }, BACK);
  }
  return success(req, "/espace/profil?ok=document#documents");
}
