import type { NextRequest } from "next/server";

import { API_URL, getMe, getToken } from "@/lib/api";

/**
 * Export CSV de la console : relaie l'API avec le jeton (qui reste côté serveur).
 * Seuls les exports connus passent, avec leurs seuls paramètres de filtre.
 */
const EXPORTS: Record<string, { path: string; params: string[] }> = {
  transactions: {
    path: "/api/console/transactions/export/",
    params: ["days", "trade", "pro", "coupon", "status"],
  },
  rapports: { path: "/api/console/reports/export/", params: [] },
};

export async function GET(req: NextRequest, ctx: { params: Promise<{ name: string }> }) {
  const { name } = await ctx.params;
  const target = Object.hasOwn(EXPORTS, name) ? EXPORTS[name] : undefined;
  if (!target) return new Response("Export inconnu.", { status: 404 });
  // Le cookie part aussi sur un lien venu d'un autre site : on n'exporte que depuis Jeflink.
  if (req.headers.get("sec-fetch-site") === "cross-site") {
    return new Response("Export à lancer depuis la console.", { status: 403 });
  }
  const token = await getToken();
  const me = token ? await getMe() : null;
  if (!token || !me?.is_staff) return new Response("Connexion requise.", { status: 401 });

  const query = new URLSearchParams();
  for (const key of target.params) {
    const value = req.nextUrl.searchParams.get(key);
    if (value) query.set(key, value);
  }
  const res = await fetch(`${API_URL}${target.path}${query.size ? `?${query}` : ""}`, {
    headers: { Authorization: `Token ${token}` },
    cache: "no-store",
  });
  if (!res.ok) {
    const message = res.status === 403 ? "Export réservé à la Finance." : "Export indisponible.";
    return new Response(message, { status: res.status });
  }
  return new Response(res.body, {
    headers: {
      "Content-Type": res.headers.get("Content-Type") ?? "text/csv; charset=utf-8",
      "Content-Disposition": res.headers.get("Content-Disposition") ?? "attachment",
      "Cache-Control": "no-store",
    },
  });
}
