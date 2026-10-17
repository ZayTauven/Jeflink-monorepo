import type { NextRequest } from "next/server";

import { relayFile } from "@/lib/relay";

/** Photo d'une demande : le client, les pros qui voient la demande, les Opérations. */
export async function GET(
  _req: NextRequest,
  ctx: { params: Promise<{ request: string; id: string }> },
) {
  const { request, id } = await ctx.params;
  if (!/^\d{1,9}$/.test(request) || !/^\d{1,9}$/.test(id)) {
    return new Response("Introuvable.", { status: 404 });
  }
  return relayFile(`/api/requests/${request}/photos/${id}/file/`);
}
