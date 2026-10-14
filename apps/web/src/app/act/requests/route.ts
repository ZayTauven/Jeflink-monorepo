import type { NextRequest } from "next/server";

import { failure, forbidden, sameOrigin, success, text } from "@/lib/actions";
import { api, getToken } from "@/lib/api";
import type { ServiceRequest } from "@/lib/types";

/** Publier une demande. */
export async function POST(req: NextRequest) {
  if (!sameOrigin(req)) return forbidden();
  const form = await req.formData();
  const res = await api<ServiceRequest>("/api/requests/", {
    method: "POST",
    token: await getToken(),
    body: {
      trade: text(form, "trade"),
      zone: text(form, "zone"),
      title: text(form, "title"),
      description: text(form, "description"),
      landmark: text(form, "landmark"),
      preferred_date: text(form, "preferred_date") || null,
      is_urgent: form.get("is_urgent") === "on",
      promo_code: text(form, "promo_code"),
      jef_session: /^\d{1,9}$/.test(text(form, "jef_session"))
        ? Number(text(form, "jef_session"))
        : null,
    },
  });
  if (!res.ok) return failure(req, res, "/espace/demandes/nouvelle");
  return success(req, `/espace/demandes/${res.data.id}`);
}
