# apps/web — site public + parcours client web

Next.js App Router, Tailwind + preset `@jeflink/ui-tokens`, next-intl (`fr`, `wo`), client API `@jeflink/api-client`.
Direction visuelle : **Crafto** (voir `docs/design/DESIGN.md`, section « Web public »).

- Server Components par défaut ; `"use client"` seulement pour l'interactivité réelle.
- SEO = canal d'acquisition majeur : pages `/[metier]/[quartier]` (ex. `/plombier/ouakam`) générées depuis catalog × zones, `generateMetadata`, sitemap dynamique, JSON-LD `Service` / `LocalBusiness`.
- Budget perf : LCP < 2,5 s en 3G rapide simulée, JS initial < 150 ko gz par page publique. `next/image` obligatoire.
- Pas de vidéo hero lourde en autoplay sur mobile (image poster + lecture à la demande).
- Photos : artisans et intérieurs sénégalais réels. Aucune image de stock occidentale générique.
- CTA principal toujours double : « Faire une demande » + « Écrire sur WhatsApp ».
