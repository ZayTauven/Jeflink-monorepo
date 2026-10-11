---
name: jeflink-design
description: Règles d'interface de Jeflink — le site reprend tel quel le template Crafto « Marketing strategy » (balisage, classes, CSS, JS, images), récit adapté. Utiliser dès qu'on crée ou modifie une page, une section, un style, un texte d'interface ou une image du site.
---

# Design Jeflink

Source de vérité : `docs/DESIGN.md`. Ce skill en est le mode d'emploi.

## Ajouter ou modifier une section

1. Trouver la section équivalente dans `references/crafto/demo-marketing-strategy*.html` et partir de son HTML.
2. Convertir en JSX **sans changer** classes ni attributs `data-*` (`data-anime`, `data-slider-options`, `data-parallax-*`, `data-bottom-top`…). Les helpers de `apps/web/src/components/crafto.tsx` produisent exactement le même balisage.
3. Remplacer le texte du template par un récit Jeflink, et les listes répétées par des données (API ou tableau en tête de page).
4. Liens internes en `<a href>`, jamais `next/link` ; boutons d'envoi sans classe `submit`.
5. Ce qui n'existe pas dans Crafto va dans `apps/web/public/jeflink.css`, dans le même esprit (rayons 20 px, pilules, `--base-color`).

## Copie

- Ton direct, chaleureux, concret : « Un plombier chez vous », pas « Solutions innovantes ».
- Verbes d'action sur les boutons (« Faire une demande », « Choisir ce devis »).
- Montants `15 000 F CFA` (`formatXOF`), dates en français à l'heure de Dakar (`formatDate`).
- Espace insécable avant `? ! : ;`.
- Aucune promesse que le produit ne tient pas encore (notifications, paiement en ligne, garantie de reprise).

## Checklist de sortie

- [ ] Balisage Crafto conservé, rendu vérifié dans le navigateur (desktop et 375 px, sans défilement horizontal)
- [ ] Aucune chaîne anglaise du template restante, aucun `placehold.co`
- [ ] Aucune fausse note, faux témoignage ou logo de partenaire inexistant ajouté
- [ ] Contraste lisible, libellés sur chaque champ, boutons nommés
