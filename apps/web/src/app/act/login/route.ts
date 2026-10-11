import type { NextRequest } from "next/server";

import { failure, forbidden, safeNext, sameOrigin, success, text } from "@/lib/actions";
import { api } from "@/lib/api";
import type { Me } from "@/lib/types";

export async function POST(req: NextRequest) {
  if (!sameOrigin(req)) return forbidden();
  const form = await req.formData();
  const res = await api<{ token: string; user: Me }>("/api/auth/login/", {
    method: "POST",
    body: { email: text(form, "email"), password: form.get("password") ?? "" },
  });
  if (!res.ok) return failure(req, res, "/connexion");
  return success(req, safeNext(form.get("suite"), "/espace"), res.data.token);
}
