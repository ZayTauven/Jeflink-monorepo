import type { NextRequest } from "next/server";

import { failure, forbidden, sameOrigin, success, text } from "@/lib/actions";
import { api } from "@/lib/api";

export async function POST(req: NextRequest) {
  if (!sameOrigin(req)) return forbidden();
  const form = await req.formData();
  const res = await api("/api/auth/contact/", {
    method: "POST",
    body: { name: text(form, "name"), email: text(form, "email"), message: text(form, "message") },
  });
  if (!res.ok) return failure(req, res, "/contact");
  return success(req, "/contact?envoye=1#formulaire");
}
