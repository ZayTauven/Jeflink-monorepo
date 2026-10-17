import type { NextRequest } from "next/server";

import { failure, forbidden, sameOrigin, success, text } from "@/lib/actions";
import { api, getToken } from "@/lib/api";

const BACK = "/espace/profil";

/** Mon profil (formulaire complet). Les champs pro sont ignorés par l'API pour un client. */
export async function POST(req: NextRequest) {
  if (!sameOrigin(req)) return forbidden();
  const form = await req.formData();
  const years = Number(text(form, "years_experience"));
  const res = await api("/api/auth/me/", {
    method: "PUT",
    token: await getToken(),
    body: {
      first_name: text(form, "first_name"),
      last_name: text(form, "last_name"),
      phone: text(form, "phone"),
      contact_pref: text(form, "contact_pref"),
      contact_hours: text(form, "contact_hours"),
      headline: text(form, "headline"),
      bio: text(form, "bio"),
      years_experience: Number.isInteger(years) ? years : 0,
      // Pro : la liste part même vide (tout décocher = aucun quartier).
      ...(form.has("zones_sent") ? { zones: form.getAll("zones").map(String) } : {}),
    },
  });
  if (!res.ok) return failure(req, res, BACK);
  return success(req, `${BACK}?ok=profil`);
}
