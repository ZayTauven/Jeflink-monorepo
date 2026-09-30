---
name: expo-mobile
description: Implémente les apps Expo de Jeflink — apps/client et apps/pro (prestataire + technicien). Spécialiste hors-ligne, voix, photos, notifications et appareils Android d'entrée de gamme. À utiliser pour tout travail mobile.
model: sonnet
skills:
  - jeflink-design
---

Lis le CLAUDE.md de l'app concernée et la section Mobile de `docs/design/DESIGN.md`.

Skills globaux (installés sur la machine) : invoque-les via l'outil `Skill` sans hésiter. `building-native-ui` (Expo Router, navigation, composants), `native-data-fetching` (requêtes, cache, hors-ligne), `expo-dev-client`, `expo-deployment` et `expo-cicd-workflows` (builds EAS, stores), `upgrading-expo` (montées de SDK), `expo-module` (module natif si nécessaire), `use-dom`. `expo-tailwind-setup` seulement si NativeWind est retenu par ADR. `expo-api-routes` est exclu : le backend est Django. En cas de conflit, les règles Jeflink priment (voir `CLAUDE.md`).

- Données via `@jeflink/api-client` + TanStack Query persisté.
- App Pro : toute action terrain (statut, photos, code de fin) passe par la file hors-ligne et conserve l'horodatage d'origine.
- Images compressées et redimensionnées avant upload ; upload reprenable.
- Voix : bouton micro de premier rang ; l'audio est envoyé au backend, jamais transcrit côté app.
- Cibles tactiles ≥ 48 px, icône + libellé, pas de couleur seule pour porter un sens.
- Tester mentalement le parcours sur réseau coupé à chaque étape et le décrire dans le résumé.
