---
name: jeflink-design
description: Règles visuelles et d'interface de Jeflink (web public inspiré de Crafto, console inspirée de Vireo mais dé-vibecodée, apps mobiles pour Android modeste). Utiliser systématiquement dès qu'on crée ou modifie un composant, une page, un écran, un style, des tokens, une copie d'interface ou une illustration — même pour une petite retouche.
---

# Design Jeflink

Source de vérité : `docs/design/DESIGN.md`. Ce skill en est le mode d'emploi.

## Avant de coder un écran

1. Quelle question métier cet écran résout-il ? Écris-la en commentaire en tête du composant de page.
2. Quelle action principale ? Une seule, avec l'accent.
3. Que voit-on quand c'est vide, en chargement, en erreur, hors-ligne ?

## Porter Crafto / Vireo

- On regarde le template pour la composition, les proportions et le rythme. On ne copie ni leur HTML, ni leur JS, ni leurs plugins jQuery.
- Reconstruire en composants Tailwind basés sur `@jeflink/ui-tokens`.
- Remplacer toute donnée de démo par des données Jeflink plausibles (quartiers de Dakar, montants en F CFA, métiers réels).
- Remplacer les images du template par celles de la banque `C:\Users\moham\Pictures\Banque` (scènes réelles au Sénégal d'abord), selon DESIGN.md › Banque d'images : copie optimisée en WebP/AVIF dans l'app, provenance dans `docs/design/assets.md`.

## Copie

- Ton direct, chaleureux, concret. « Un plombier chez vous aujourd'hui » plutôt que « Solutions de services innovantes ».
- Verbes d'action sur les boutons (« Envoyer ma demande », « Valider le devis »).
- Montants `25 000 F CFA`, jamais de décimales. Dates en français, heure de Dakar.

## Checklist de sortie

- [ ] Aucun pattern interdit de DESIGN.md (glass, aurora, dégradés décoratifs, emojis UI, avatars de démo, KPI en rafale, badges gratuits)
- [ ] Uniquement des tokens (couleurs, rayons, ombres, espacements)
- [ ] Chaînes dans i18n
- [ ] Contraste AA, cibles ≥ 48 px sur mobile, sens pas porté par la couleur seule
- [ ] États vide / chargement / erreur / hors-ligne traités
- [ ] Images en WebP/AVIF aux tailles affichées, chacune listée dans `docs/design/assets.md` avec sa licence
