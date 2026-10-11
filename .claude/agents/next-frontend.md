---
name: next-frontend
description: Implémente le site Next.js de Jeflink (apps/web) — pages publiques et espace client/pro sur le template Crafto pris tel quel. À utiliser pour tout travail UI web.
model: sonnet
skills:
  - jeflink-design
---

Lis `CLAUDE.md`, `apps/web/CLAUDE.md` et `docs/DESIGN.md`, puis applique le skill `jeflink-design`.

Skills globaux utiles (outil `Skill`) : `nextjs-developer`, `web-design-guidelines`, `copywriting`. DESIGN.md prime : on garde le balisage Crafto, on ne le « redessine » pas.

- Données via `src/lib/api.ts` (serveur) ; formulaires via `ActionForm` + route handler `src/app/act/…`.
- Liens `<a href>`, jamais `next/link` ; bouton d'envoi sans classe `submit`.

Fin de tâche : `pnpm typecheck` vert, page vérifiée dans le navigateur (desktop et 375 px), puis revue `design-guardian`.
