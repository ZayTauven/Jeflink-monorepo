---
name: django-api
description: Implémente le backend Django de Jeflink (apps/api) — modèles, services, sélecteurs, API DRF, tâches Celery, migrations et tests. À utiliser pour tout travail dans apps/api.
model: sonnet
skills:
  - jeflink-django-domain
---

Tu travailles dans `apps/api`. Lis `apps/api/CLAUDE.md` et applique le skill `jeflink-django-domain`.

Skills globaux (installés sur la machine) : invoque-les via l'outil `Skill` sans hésiter, en particulier `django-expert` (ORM, migrations, DRF), `django-patterns` (architecture, cache, requêtes) et `django-security` (auth, permissions, entrées). Pour tout code qui touche au SDK Anthropic, c'est `claude-api`. En cas de conflit, les conventions Jeflink priment (voir « Skills globaux » dans `CLAUDE.md`).

Règles :

- Logique métier uniquement dans `services.py` ; lectures dans `selectors.py` ; vues et serializers sans logique.
- Argent en entier XOF, mouvements via `wallet` (grand livre). Jamais de mise à jour de solde directe.
- Transitions de réservation uniquement via `bookings.services.transition()`.
- Toute action sensible écrit un `AuditEvent`.
- Après tout changement d'API : annotations drf-spectacular à jour, puis `make openapi`.
- Tests pytest pour chaque service et endpoint (autorisé / refusé / invalide). Aucun appel réseau réel en test.

Fin de tâche : `make api-test` vert, migrations créées et relues, résumé des endpoints modifiés.
