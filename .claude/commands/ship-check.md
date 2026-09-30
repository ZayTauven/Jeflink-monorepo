---
description: Checklist avant PR
---

Vérifie et rapporte sous forme de checklist :

- [ ] `make api-test` vert
- [ ] `pnpm lint && pnpm typecheck` verts
- [ ] migrations créées, relues, sans opération destructive non annoncée
- [ ] `make openapi` exécuté si l'API a changé, client régénéré commité
- [ ] aucune chaîne en dur (clés i18n `fr` présentes)
- [ ] revue `design-guardian` si UI modifiée
- [ ] revue `security-reviewer` si argent / KYC / auth / permissions touchés
- [ ] message de commit Conventional Commits avec scope

Corrige ce qui est trivial, liste le reste.
