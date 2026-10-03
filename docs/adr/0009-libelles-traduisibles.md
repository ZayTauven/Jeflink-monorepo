# ADR 0009 — Libellés de données traduisibles : une colonne par langue

Statut : proposé · 2026-10-03 · Spec : `docs/specs/002-catalog-zones.md`

## Contexte

Les métiers et les services sont des données saisies par l'Ops (`CLAUDE.md`, PRODUCT.md §7), et leurs libellés s'affichent en `fr` et en `wo`. D'autres données de référence suivront le même chemin : motifs d'annulation, catégories de litige, critères d'avis. Au lancement, le `wo` sera souvent absent. Les apps tournent sur des téléphones modestes, avec un réseau cher et instable, et gardent ce référentiel en cache. Les pages SEO sont générées depuis la base.

## Décision

- Un champ traduisible devient une colonne par langue : `<champ>_fr` obligatoire, `<champ>_wo` optionnel (vide permis). Les noms propres, comme les quartiers, gardent un seul champ.
- L'API expose un objet `LocalizedText = {fr: string, wo: string | null}`, composant OpenAPI unique. Le front choisit la langue et retombe sur `fr` si `wo` est nul.
- Ces endpoints ne négocient pas la langue (pas d'`Accept-Language`, pas de `?lang=`) : une seule réponse cacheable, et changer de langue dans l'app ne demande aucun appel.
- Ajouter une langue reste un changement de code (migration et fronts). C'est voulu : une langue n'est pas une donnée métier.

## Conséquences

- L'admin Django affiche les deux champs sans dépendance, et une `CheckConstraint` simple garantit le `fr`.
- Une traduction `wo` manquante se voit dans l'admin (filtre « wo vide ») et ne bloque jamais l'affichage.
- − Le poids des réponses double pour les libellés. C'est négligeable pour des listes bornées de quelques dizaines de lignes.
- − Une troisième langue demandera une migration par modèle traduisible.

## Alternatives écartées

- **`django-modeltranslation` ou `django-parler`** : une dépendance et de la magie (champs dynamiques, requêtes réécrites) pour seulement deux langues.
- **`JSONField` `{fr, wo}`** : plus souple pour ajouter une langue, mais le `fr` obligatoire est moins net en base, et la saisie dans l'admin est moins bonne.
- **Résolution côté serveur par `Accept-Language`** : cache fragmenté (`Vary`), nouvel appel à chaque changement de langue, et un risque de mauvaise négociation sur les navigateurs réglés en anglais.
