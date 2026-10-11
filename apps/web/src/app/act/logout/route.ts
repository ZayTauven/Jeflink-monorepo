import type { NextRequest } from "next/server";

import { forbidden, sameOrigin, success } from "@/lib/actions";
import { api, getToken } from "@/lib/api";

export async function POST(req: NextRequest) {
  if (!sameOrigin(req)) return forbidden();
  const token = await getToken();
  if (token) await api("/api/auth/logout/", { method: "POST", token });
  return success(req, "/", null);
}
