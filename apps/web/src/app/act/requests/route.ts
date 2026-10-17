import type { NextRequest } from "next/server";

import { failure, forbidden, sameOrigin, success, text } from "@/lib/actions";
import { api, getToken } from "@/lib/api";
import type { ServiceRequest } from "@/lib/types";

const BACK = "/espace/demandes/nouvelle";
const MAX_PHOTOS = 3;
// 3 photos de 8 Mo au plus (sans JavaScript, elles partent sans être réduites) et le texte.
const MAX_BODY = 26 * 1024 * 1024;

/** Publier une demande, puis y joindre ses photos (3 au plus). */
export async function POST(req: NextRequest) {
  if (!sameOrigin(req)) return forbidden();
  // Connexion et taille vérifiées avant de lire le corps. Un navigateur annonce toujours la
  // taille d'un formulaire : sans elle (envoi « chunked »), refus.
  const token = await getToken();
  if (!token) return success(req, `/connexion?suite=${BACK}`, null);
  const length = Number(req.headers.get("content-length"));
  if (!(length > 0) || length > MAX_BODY) {
    const error = "Photos trop lourdes : 8 Mo au plus chacune.";
    return failure(req, { ok: false, status: 413, error, fields: {} }, BACK);
  }
  const form = await req.formData();
  const res = await api<ServiceRequest>("/api/requests/", {
    method: "POST",
    token,
    body: {
      trade: text(form, "trade"),
      zone: text(form, "zone"),
      title: text(form, "title"),
      description: text(form, "description"),
      landmark: text(form, "landmark"),
      preferred_date: text(form, "preferred_date") || null,
      is_urgent: form.get("is_urgent") === "on",
      promo_code: text(form, "promo_code"),
      save_address: text(form, "save_address"),
      jef_session: /^\d{1,9}$/.test(text(form, "jef_session"))
        ? Number(text(form, "jef_session"))
        : null,
    },
  });
  if (!res.ok) return failure(req, res, BACK);

  // La demande est publiée : une photo refusée ne doit pas la faire republier (doublon). On
  // arrive sur la demande avec le message, le client peut y rajouter la photo.
  const here = `/espace/demandes/${res.data.id}`;
  const photos = form
    .getAll("photos")
    .filter((p): p is File => p instanceof File && p.size > 0)
    .slice(0, MAX_PHOTOS);
  for (const photo of photos) {
    const body = new FormData();
    body.append("photo", photo);
    const sent = await api(`/api/requests/${res.data.id}/photos/`, { method: "POST", token, body });
    if (!sent.ok) {
      const why = sent.fields.photo || sent.error || "photo illisible";
      const message = `Demande publiée, mais une photo n'a pas pu être jointe : ${why}`;
      return success(req, `${here}?erreur=${encodeURIComponent(message)}#photos`);
    }
  }
  return success(req, here);
}
