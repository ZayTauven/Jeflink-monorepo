---
description: Cadrer une nouvelle feature Jeflink (spec + revue terrain), sans coder
argument-hint: <nom ou description de la feature>
---

Feature demandée : $ARGUMENTS

1. Avec l'agent `architect`, rédige la spec dans `docs/specs/NNN-<slug>.md` (numéro suivant le plus élevé existant), en suivant `docs/specs/_TEMPLATE.md`.
2. Fais relire la spec par l'agent `terrain-reviewer` et intègre ses changements prioritaires s'ils sont dans le périmètre de la phase.
3. Si l'argent, le KYC ou l'auth sont touchés, ajoute une section « Points de sécurité » après passage de `security-reviewer`.
4. Présente-moi un résumé en 10 lignes maximum et la liste des questions à trancher.

N'écris aucun code applicatif avant ma validation explicite.
