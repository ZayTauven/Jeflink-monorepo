// Balise JSON-LD. Un bloc `application/ld+json` n'est pas exécuté : la CSP (script-src à nonce)
// ne le bloque pas. `<` est échappé par `serializeJsonLd` (recommandation de la doc de Next).
import { type JsonLd, serializeJsonLd } from "@/lib/site/jsonld";

export function JsonLdScript({ data }: { data: JsonLd }) {
  return (
    <script
      type="application/ld+json"
      dangerouslySetInnerHTML={{ __html: serializeJsonLd(data) }}
    />
  );
}
