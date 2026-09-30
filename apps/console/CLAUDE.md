# apps/console — back-office Ops + Pro

Next.js App Router. Ossature inspirée de Vireo, **reconstruite** en Tailwind + tokens Jeflink (on ne copie pas le HTML/JS du template).
Deux espaces : `/ops/*` (équipe Jeflink, RBAC fin) et `/pro/*` (prestataires sur desktop).

- Données : TanStack Query via `@jeflink/api-client` ; tableaux : TanStack Table ; graphiques : une seule lib (Recharts).
- Auth : route handlers Next en BFF, tokens en cookies httpOnly. Jamais de token dans localStorage.
- Chaque écran répond à UNE question métier (ex. « Quels litiges dois-je traiter aujourd'hui ? »). Pas de dashboard décoratif.
- Maximum 4 KPI en tête d'écran, chacun cliquable vers la liste filtrée correspondante.
- Command palette ⌘K : gardée (vraie valeur pour l'Ops). Customizer de thème : supprimé.
- Mode sombre : oui (console uniquement en V1).
- Relire la section « Dé-vibecoder Vireo » de DESIGN.md avant tout écran.
