# ADR 0004 — IA exclusivement côté serveur

Statut : accepté · 2026-09-30

## Décision

Toute capacité IA vit dans le domaine `ai` du backend : prompts versionnés, sorties validées, repli sans IA, journal `AIRun` (coût, latence, version), jeu d'évaluation par capacité. Les fronts et apps n'appellent jamais un LLM.

## Conséquences

- Clés protégées, coûts maîtrisés, données minimisées avant envoi.
- Changer de modèle ou de fournisseur sans toucher aux clients.
  − Latence réseau supplémentaire acceptée.
