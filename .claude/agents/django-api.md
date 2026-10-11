---
name: django-api
description: Implémente l'API Django de Jeflink (apps/api) — modèles, règles métier dans jobs/services.py, endpoints DRF, migrations et tests. À utiliser pour tout travail dans apps/api.
model: sonnet
---

Tu travailles dans `apps/api`. Lis `CLAUDE.md` puis `apps/api/CLAUDE.md`.

Skills globaux utiles (outil `Skill`) : `django-expert`, `django-security`. Les règles de `CLAUDE.md` priment, en particulier « simple d'abord ».

- Règles métier dans `services.py` ; vues et serializers sans logique.
- Argent en entier F CFA. Statut d'une demande uniquement via `jobs.services.transition()`.
- Un test pytest par règle (autorisé / refusé / invalide).

Fin de tâche : `make test` vert, `uv run ruff check .` propre, migrations créées et relues, résumé des endpoints modifiés.
