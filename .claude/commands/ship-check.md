---
description: Checklist avant PR
---

Vérifie et rapporte sous forme de checklist :

- [ ] `make test` vert et `uv run --directory apps/api ruff check .` propre
- [ ] `pnpm typecheck` vert
- [ ] migrations créées et relues
- [ ] parcours touché vérifié dans le navigateur
- [ ] revue `design-guardian` si UI modifiée, `security-reviewer` si auth / permissions / données perso
- [ ] message de commit Conventional Commits avec scope

Corrige ce qui est trivial, liste le reste.
