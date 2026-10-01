// Montage du BFF (spec 001, « BFF Next ») : toute requête /api/* passe par `bff().handle()`, qui
// sert les endpoints de jetons et proxifie le reste vers Django (proxy durci, CSRF, cookies).
import { bff } from "@/lib/bff";

// Jamais de rendu statique ni de cache : chaque réponse dépend des cookies de la requête.
export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const handle = (request: Request): Promise<Response> => bff().handle(request);

export {
  handle as DELETE,
  handle as GET,
  handle as HEAD,
  handle as PATCH,
  handle as POST,
  handle as PUT,
};
