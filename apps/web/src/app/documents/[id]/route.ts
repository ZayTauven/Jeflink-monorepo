import type { NextRequest } from "next/server";

import { API_URL, getToken } from "@/lib/api";

/**
 * Fichier d'un document de pro (pièce d'identité, attestation) : relayé depuis l'API avec le
 * jeton du cookie. L'API décide qui y a droit (le pro lui-même, l'équipe Opérations) ; ici on
 * ne fait que transmettre, sans cache, avec ses en-têtes de sécurité.
 */
const KEEP = [
  "content-type",
  "content-disposition",
  "content-length",
  "cache-control",
  "content-security-policy",
  "x-content-type-options",
];

export async function GET(_req: NextRequest, ctx: { params: Promise<{ id: string }> }) {
  const { id } = await ctx.params;
  const token = await getToken();
  if (!/^\d{1,9}$/.test(id) || !token) return new Response("Introuvable.", { status: 404 });
  let res: Response;
  try {
    res = await fetch(`${API_URL}/api/auth/documents/${id}/file/`, {
      headers: { Authorization: `Token ${token}` },
      cache: "no-store",
    });
  } catch {
    return new Response("L'API Jeflink ne répond pas.", { status: 503 });
  }
  if (!res.ok || !res.body) return new Response("Introuvable.", { status: 404 });
  const headers = new Headers();
  for (const name of KEEP) {
    const value = res.headers.get(name);
    if (value) headers.set(name, value);
  }
  return new Response(res.body, { status: 200, headers });
}
