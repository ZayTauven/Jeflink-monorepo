import type { NextRequest } from "next/server";

import { failure, forbidden, sameOrigin, success, text } from "@/lib/actions";
import { api, getToken } from "@/lib/api";

const BACK = "/espace/profil#adresses";

/** Ajouter une adresse à « Mes adresses ». */
export async function POST(req: NextRequest) {
  if (!sameOrigin(req)) return forbidden();
  const form = await req.formData();
  const res = await api("/api/auth/me/addresses/", {
    method: "POST",
    token: await getToken(),
    body: {
      label: text(form, "label"),
      zone: text(form, "zone"),
      landmark: text(form, "landmark"),
    },
  });
  if (!res.ok) return failure(req, res, BACK);
  return success(req, "/espace/profil?ok=adresse#adresses");
}
