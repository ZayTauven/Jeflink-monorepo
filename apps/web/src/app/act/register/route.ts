import type { NextRequest } from "next/server";

import { failure, forbidden, safeNext, sameOrigin, success, text } from "@/lib/actions";
import { api } from "@/lib/api";
import type { Me } from "@/lib/types";

export async function POST(req: NextRequest) {
  if (!sameOrigin(req)) return forbidden();
  const form = await req.formData();
  const role = text(form, "role") === "pro" ? "pro" : "client";
  const res = await api<{ token: string; user: Me }>("/api/auth/register/", {
    method: "POST",
    body: {
      role,
      email: text(form, "email"),
      password: form.get("password") ?? "",
      first_name: text(form, "first_name"),
      last_name: text(form, "last_name"),
      phone: text(form, "phone"),
      ...(role === "pro"
        ? {
            headline: text(form, "headline"),
            trades: form.getAll("trades"),
            zones: form.getAll("zones"),
          }
        : {}),
    },
  });
  if (!res.ok) return failure(req, res, `/inscription${role === "pro" ? "?role=pro" : ""}`);
  return success(req, safeNext(form.get("suite"), "/espace"), res.data.token);
}
