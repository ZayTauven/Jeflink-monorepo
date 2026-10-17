import type { NextRequest } from "next/server";

import { relayFile } from "@/lib/relay";

/** Fichier d'un document de pro (pièce d'identité, attestation) : le pro ou les Opérations. */
export async function GET(_req: NextRequest, ctx: { params: Promise<{ id: string }> }) {
  const { id } = await ctx.params;
  if (!/^\d{1,9}$/.test(id)) return new Response("Introuvable.", { status: 404 });
  return relayFile(`/api/auth/documents/${id}/file/`);
}
