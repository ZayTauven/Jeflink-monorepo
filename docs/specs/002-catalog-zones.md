# Spec 002 — catalog et zones : métiers, services, quartiers

Statut : brouillon · 2026-10-03 · ADR lié : 0009 (libellés traduisibles, proposé) · Revue `terrain-reviewer` intégrée (Q1 à Q6 acceptées avec réserves)

## Problème

La demande (spec 003), le matching, l'IA de structuration (IA1) et les pages SEO `/[metier]/[quartier]` ont tous besoin du même référentiel : quels métiers Jeflink propose, dans quels quartiers, et ce qu'on y fait. PRODUCT.md §7 l'impose comme **données** : ajouter un vitrier ou ouvrir Keur Massar est une saisie Ops, sans migration ni déploiement. La console Ops n'existe pas encore : l'admin Django sert d'outil de saisie au départ.

| Zone sensible                    | Touchée ? | Détail                                                                                                                                   |
| -------------------------------- | --------- | ---------------------------------------------------------------------------------------------------------------------------------------- |
| Argent                           | Non       | Un prix « à partir de » indicatif, en entier XOF, affiché seulement. Aucun mouvement, aucun `LedgerEntry`.                               |
| KYC                              | Non       |                                                                                                                                          |
| Machine à états des réservations | Non       | Aucune transition.                                                                                                                       |
| Auth, admin                      | Oui, peu  | L'admin Django devient **modifiable** pour les seuls modèles `catalog` et `zones`. Le reste reste en lecture seule. Aucune donnée perso. |

## Parcours

- **Ops (admin Django, second facteur TOTP déjà en place).** Crée ou modifie un métier, ses services et leurs alias. Saisit un quartier (nom, alias, point central sur la carte, rayon) et coche les métiers ouverts dans ce quartier. Ne supprime jamais : il désactive. Le slug est figé après création.
- **Client (web, app, plus tard WhatsApp).** Cherche un métier ou un quartier avec ses propres mots (« frigoriste », « PA »), y compris hors ligne. Voit les métiers ouverts chez lui. Le détail d'un métier montre ses services et, si l'Ops l'a saisi, un « à partir de ». Son quartier n'est pas dans la liste : il choisit « Autre quartier / je ne sais pas » et l'écrit librement. Ce n'est **jamais un cul-de-sac**, la spec 003 accepte la demande et l'Ops la rattache.
- **Front SEO (étape 6).** Construit `/[metier]/[quartier]` à partir du détail métier, qui liste les quartiers où il est ouvert.

**Pourquoi un niveau « service » dès la V1** (léger : 4 à 6 par métier, optionnel dans la demande) :

1. **Prix.** Un « à partir de » n'a de sens que par service. Déboucher un évier et refaire une salle de bain n'ont rien en commun.
2. **Demande.** Un choix en un geste aide Ibou et Awa, qui écrivent peu. Le drapeau `urgent` sert le tri de la spec 003, et l'IA1 peut proposer le service à partir de la note vocale.
3. **SEO.** La page `/plombier/ouakam` liste « ce qu'on fait » avec de vrais termes de recherche. Les URL restent métier × quartier.

## Réalité terrain

- **Les mots des clients.** Métiers, services et zones portent des `aliases`. Ce sont des chaînes libres, sans langue : un terme wolof validé s'y ajoute par simple saisie. Les slugs sont en ASCII sans accent.
- **Une seule normalisation**, `jeflink.common.search.normalize()`, partagée par l'API, l'IA1 et les fronts :
  1. NFKD et retrait des diacritiques ; `œ` devient `oe`, `æ` devient `ae` ;
  2. minuscules ;
  3. apostrophes, tirets, points et ponctuation remplacés par des espaces, espaces fusionnés ;
  4. une forme compacte, sans espaces, est comparée aussi (« pattedoie »).

  Règle de correspondance `match(query, terms)` : à partir de 3 caractères, préfixe d'un terme ou d'un de ses mots (« parcelle » trouve « Parcelles Assainies ») ; sous 3 caractères, égalité stricte avec un terme (« PA »). Résultats classés : égalité, préfixe du terme, préfixe d'un mot, puis `position`. Un alias peut viser deux métiers (« frigo ») : la recherche montre les deux et le client choisit. Le miroir TS (`packages/api-client/src/search/`) et le Python passent les mêmes vecteurs de test (un seul fichier JSON).

- **Réseau faible.** Un appel par liste, quelques ko, listes bornées sans pagination, `ETag` et `Cache-Control` publics. Les apps gardent le référentiel en cache et y cherchent hors ligne.
- **Langues.** Libellés `fr` obligatoires, `wo` **laissés vides** : aucune traduction wolof n'est figée sans validation par un locuteur. Repli sur `fr` (ADR 0009).
- **Adressage par repères.** Cette spec ne fournit que la **zone**. Le repère, la photo et la note vocale relèvent de la spec 003. La zone vient du quartier choisi, du texte libre, ou d'un point GPS traité côté serveur seulement. Aucune coordonnée d'utilisateur n'est reçue par les endpoints de cette spec, ni journalisée.
- **Pictogrammes.** Jamais d'icône seule : toujours avec un libellé court (règle pour tous les fronts). Un métier sans pictogramme dédié prend le pictogramme générique.

## Modèle de données et API

### Modèles

Tous héritent de `BaseModel`. Pas de `choices` ni d'`enum` pour les métiers ou les zones. Le **slug** est l'identifiant public de ces données de référence (immuable, URL SEO, IA) ; `public_id` n'est pas exposé. `aliases` : `ArrayField` de chaînes de 40 caractères au plus, optionnel, même mécanisme sur les trois modèles.

| Modèle                             | Champs                                                                                                                                                                                                                                                                                                                                                                                                                                                                 |
| ---------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `catalog.Trade` (métier)           | `slug` (unique, `^[a-z0-9]+(-[a-z0-9]+)*$`, 50 car., figé, refusé s'il figure dans `RESERVED_TRADE_SLUGS` : `connexion`, `api`, `compte`…) · `name_fr`/`name_wo` (60) · `short_description_fr`/`_wo` (160, optionnels) · `seo_title_fr`/`_wo` (70, optionnels : H1 et titre SEO, repli sur le nom) · `aliases` · `icon_key` (optionnel) · `is_active` · `position`                                                                                                     |
| `catalog.Service`                  | `trade` (FK, `PROTECT`) · `slug` (unique par métier) · `name_fr`/`name_wo` (80) · `aliases` · `price_from_xof` (`PositiveBigIntegerField`, nul permis) · `urgent` (booléen, défaut faux) · `is_active` · `position`                                                                                                                                                                                                                                                    |
| `zones.City`                       | `name` · `slug` (unique) · `is_active`. Une seule ligne en V1 : Dakar (région, banlieue comprise).                                                                                                                                                                                                                                                                                                                                                                     |
| `zones.Zone` (quartier ou commune) | `city` (FK, `PROTECT`) · `name` (80, nom propre sans traduction) · `slug` (**unique global** : l'URL ne porte pas la ville) · `aliases` · `center` (`PointField(srid=4326)`, obligatoire) · `radius_m` (défaut 1 500, `CheckConstraint` 200 à 15 000) · `boundary` (`MultiPolygonField`, nul permis, prime sur le cercle s'il est saisi) · `trades` (`ManyToManyField(catalog.Trade)` : métiers ouverts, opt-in, Q4) · `position` (popularité, puis nom) · `is_active` |

**Prix : un seul champ `price_from_xof`.** On n'affiche qu'un « à partir de », et une vraie fourchette viendra des devis réels (IA2, V2), pas d'une saisie.

Géométrie : centre + rayon suffit au matching par distance (PostGIS `geography`) et au SEO, sans relever des polygones avant de coder. Un `boundary` approximatif reste optionnel, même pour Pikine, Guédiawaye, Keur Massar et Rufisque.

### Sélecteurs (contrat pour les specs suivantes)

- `zones.selectors.zones_for_point(point) -> list[Zone]` : zones actives dont le `boundary` contient le point, sinon zones dont le cercle le contient, triées par distance au centre. Aucune → hors zone. **Plusieurs → le client choisit** (« Pikine ou Guédiawaye ? ») : jamais de choix automatique silencieux.
- `zones.selectors.resolve_zone_text(text) -> list[Zone]` : candidates trouvées par `match()` sur les noms et les alias.
- `zones.selectors.availability(*, trade_slug, zone_slug=None, zone_text=None) -> Availability` : `available` ou un motif stable parmi `trade_not_found`, `trade_inactive`, `zone_not_found` (slug inexistant), `zone_inactive`, `trade_not_in_zone`, `zone_unknown` (texte libre sans zone reconnue) et `out_of_area` (point GPS hors zone). Pour `zone_unknown`, il renvoie aussi le texte normalisé, chiffres retirés et coupé à 40 caractères.
- `catalog.selectors.active_trades()` : métiers et services actifs, avec alias, en une requête (`prefetch_related`). C'est la liste que l'IA1 recevra (spec 003).

Disponible = métier actif, zone et ville actives, métier coché dans la zone. En V1, c'est un interrupteur Ops, indépendant de la présence de pros (le lien viendra avec `providers`).

### Endpoints

Tags `catalog` et `zones`. Tous `AllowAny`, `GET` seulement, `rate_limit_scope = "catalog_read"` (`IP_RATE_LIMITS` : 600 / 60 s pour le CGNAT ; fermée si Redis tombe). Libellés en `LocalizedText = {fr, wo | null}` (ADR 0009). Listes bornées sans pagination (`REFERENCE_LIST_MAX = 200`, test). `Cache-Control: public, max-age=300, stale-while-revalidate=86400` et `ETag` (304). Un appel avec jeton garde `private, no-store` (`NoStoreMiddleware` inchangé) : les fronts appellent **sans jeton**.

| Méthode | Chemin                        | Réponse                                                                                                                                                                    |
| ------- | ----------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| GET     | `/api/catalog/trades/`        | `[{slug, name, short_description, icon_key, aliases}]`, métiers actifs par `position`                                                                                      |
| GET     | `/api/catalog/trades/{slug}/` | `{…liste, seo_title, services[{slug, name, aliases, price_from_xof, urgent}], zones[slug]}` ; `zones` = zones actives où le métier est ouvert. Sinon `404 trade_not_found` |
| GET     | `/api/zones/`                 | `[{slug, name, city, aliases}]`, zones actives de villes actives, par `position` puis nom. Filtre `?city=<slug>`                                                           |
| GET     | `/api/zones/{slug}/trades/`   | Métiers ouverts dans la zone, forme de la liste. Sinon `404 zone_not_found`                                                                                                |

Codes d'erreur i18n ajoutés : `trade_not_found`, `zone_not_found`. Ni position, ni polygone dans les réponses. Tout prix affiché porte la mention en toutes lettres « prix de départ, le prix final est dans le devis » (clé i18n des fronts).

### Admin Django (outil de saisie Ops)

- `Trade` avec `Service` en inline ; `City` ; `Zone` en `GISModelAdmin` (carte pour le centre, et le `boundary` si besoin), `trades` en cases à cocher. Action « Ouvrir dans toutes les zones actives » sur `Trade`. Filtre « wo vide ».
- Aucune suppression (`has_delete_permission = False`) : on désactive. Slugs en lecture seule après création. Validation dans `clean()` et contraintes en base ; `save_model` passe par `catalog.services` et `zones.services`.
- Droits : permissions `add` et `change`, réunies dans un groupe `Saisie catalogue` créé par migration. Le compte qui saisit est un **compte technique** (`is_staff`) : l'invariant « technique ≠ ops » de la spec 001 tient (Q6).
- Traçabilité : l'historique de l'admin (`LogEntry`) suffit, ce ne sont pas des actions sensibles. Pas d'`AuditEvent`.

### Données de départ

Commande `manage.py seed_reference_data`, idempotente : elle crée ce qui manque (par slug) et **n'écrase jamais** une saisie Ops. Données dans un module versionné du domaine ; `wo` vides, prix vides (Q3). Les tests partent d'une base vide (fabriques).

| Métier (slug : Q1)                       | Alias                                                                      | Services (★ = `urgent`)                                                                                                                |
| ---------------------------------------- | -------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------- |
| Plomberie (`plombier`)                   | plombier, WC qui coule, chasse, fuite                                      | fuite et robinetterie ★, débouchage (évier, WC, douche), chasse d'eau, chauffe-eau, pompe et surpresseur, pose de sanitaires           |
| Électricité (`electricien`)              | électricien, tableau électrique, disjoncteur, compteur, coupure de courant | panne et coupure de courant ★, prises et interrupteurs, éclairage, tableau et disjoncteurs, ventilateur de plafond, raccordement       |
| Froid et climatisation (`climatisation`) | frigoriste, clim, climatiseur, frigo                                       | entretien de clim, panne de clim, recharge de gaz, pose de split, frigo ou congélateur en panne ★ (Q2)                                 |
| Électroménager (`electromenager`)        | frigo, machine, dépannage, réparateur                                      | machine à laver, cuisinière et four, micro-ondes, petit électroménager                                                                 |
| Ménage (`menage`)                        | femme de ménage, nettoyage                                                 | ménage ponctuel, grand nettoyage (fin de travaux, déménagement), canapés et matelas. `seo_title_fr` : « Femme de ménage et nettoyage » |
| Petits travaux (`petits-travaux`)        | bricolage, bricoleur, peintre                                              | peinture, menuiserie (portes, meubles), maçonnerie légère et carrelage, montage de meubles, fixations (étagères, tringles, TV)         |

Ville : Dakar. **24 zones** (grain : Q5). Les centres sont relevés sur OpenStreetMap et vérifiés sur la carte de l'admin. Rayon de 1 500 m pour un quartier de Dakar, de 3 000 à 5 000 m pour une commune de banlieue. `position` : Parcelles Assainies 1, Pikine 2, Guédiawaye 3, Ouakam 4 ; les autres 100, puis tri par nom.

| Zone (slug)                                 | Alias                                                          |
| ------------------------------------------- | -------------------------------------------------------------- |
| Parcelles Assainies (`parcelles-assainies`) | Parcelles, PA, Unité 15                                        |
| Pikine (`pikine`)                           | Thiaroye, Dalifort, Diamaguène, Mbao                           |
| Guédiawaye (`guediawaye`)                   | Golf Sud, Sam Notaire, Médina Gounass                          |
| Ouakam (`ouakam`)                           |                                                                |
| Almadies (`almadies`)                       |                                                                |
| Cambérène (`camberene`)                     |                                                                |
| Dieuppeul – Derklé (`dieuppeul-derkle`)     | Dieuppeul, Derklé                                              |
| Fann (`fann`)                               |                                                                |
| Fass – Colobane (`fass-colobane`)           | Fass, Colobane                                                 |
| Grand Dakar (`grand-dakar`)                 |                                                                |
| Grand Yoff (`grand-yoff`)                   |                                                                |
| Hann Bel-Air (`hann-bel-air`)               | Hann, Bel Air, Maristes                                        |
| HLM (`hlm`)                                 | HLM Grand Yoff, HLM Paris                                      |
| Keur Massar (`keur-massar`)                 | Malika                                                         |
| Liberté (`liberte`)                         | Sicap, Sicap Liberté, Sicap Baobab, Sicap Karack, Sicap Amitié |
| Médina (`medina`)                           |                                                                |
| Mermoz (`mermoz`)                           |                                                                |
| Ngor (`ngor`)                               | Ngor Village                                                   |
| Patte d'Oie (`patte-doie`)                  | Patte d'oie, Patte Doie, Pattedoie                             |
| Plateau (`plateau`)                         | Sandaga, Dakar centre, Dakar Plateau                           |
| Point E (`point-e`)                         |                                                                |
| Rufisque (`rufisque`)                       |                                                                |
| Sacré-Cœur (`sacre-coeur`)                  | Sacré-Cœur 1, Sacré-Cœur 2, Sacré-Cœur 3                       |
| Yoff (`yoff`)                               | Yoff Layène                                                    |

**Gorée : pas dans le seed V1.** On n'y accède qu'en chaloupe : le trajet et le coût de déplacement ne sont pas modélisés, la population est faible et le pro y reste bloqué par les horaires. « Gorée » saisi en texte libre donne `zone_unknown` et alimente le signal ; l'Ops ouvre la zone par une saisie si la demande existe (Q5).

Disponibilité : en `local`, tout est ouvert partout. Avant le lancement, l'Ops ajuste selon les pros recrutés.

### Hook « demande non servie » (IA7)

Rien n'est enregistré ici. `analytics` attendra un événement `demand.unserved`, sans identifiant d'utilisateur : `{trade_slug | null, zone_slug | null, reason (motif d'availability), zone_text (normalisé, pour zone_unknown seulement), channel, occurred_at}`. Pour `out_of_area`, la zone la plus proche et une distance arrondie au kilomètre, jamais le point GPS. Un métier hors catalogue (« vitrier ») arrivera par l'IA1, normalisé par `normalize()`. L'émission se fera dans la spec 003 et dans la spec `analytics`.

### Transitions de réservation touchées

Aucune.

## IA (si applicable)

Rien n'est livré ici. La spec 003 passera `active_trades()` à l'IA1 : slugs, libellés `fr` et alias, jamais une liste en dur dans un prompt. Un terme proposé par l'IA est résolu en slug par `normalize()` et `match()`. **`price_from_xof` n'est jamais transmis à l'IA** comme valeur à restituer au client.

## Hors périmètre

- Écrans Ops de la console Next (après son BFF et son TOTP, `chantier-prod.md`).
- Pages SEO, sitemap, JSON-LD : étape 6. Les slugs remplacés y seront servis par une redirection 301 depuis un alias de slug.
- Endpoint « quel est mon quartier ? » à partir d'un point GPS : la spec 003 décidera (`POST` authentifié, jamais de coordonnées dans l'URL).
- Envoi d'images (pas de stockage d'objets branché à Django) ; zones imbriquées ; villes hors Dakar (déjà possibles par saisie).
- Fourchettes calculées (IA2, V2), zones de couverture des pros, frais de déplacement ; `requires_visit` et durée d'un service (spec 003).
- Cache CDN et purge à la modification : `chantier-prod.md`.

## Critères d'acceptation

- [ ] Un métier, un service ou une zone créé dans l'admin apparaît dans l'API sans migration ni déploiement. Désactivé, il disparaît des listes et son détail répond 404.
- [ ] Aucun `choices`, `enum` ou liste de métiers ou de quartiers dans le code applicatif, hors module de données de départ.
- [ ] L'admin refuse la suppression et la modification d'un slug, ainsi qu'un slug réservé ou mal formé.
- [ ] « PA », « parcelle », « Sacre Coeur », « Sicap » et « frigoriste » retrouvent la bonne zone ou le bon métier, en Python comme en TS (vecteurs partagés).
- [ ] `zones_for_point` : point dans un `boundary`, point dans un cercle, **deux cercles qui se chevauchent → deux candidates triées**, point hors zone → liste vide.
- [ ] `availability` : un test par motif, dont `zone_unknown` avec un texte normalisé sans chiffres.
- [ ] Les 4 endpoints répondent sans authentification, avec `Cache-Control` public et `ETag` (304 testé). Avec un jeton : `private, no-store`. `POST` → 405. Limite `catalog_read` déclarée (test S29).
- [ ] Un libellé `wo` vide sort en `null`. Un prix nul n'est pas affiché.
- [ ] `seed_reference_data` lancé deux fois ne crée aucun doublon et n'écrase pas une saisie de l'admin.
- [ ] `make openapi` à jour, client TS régénéré.

## Tâches par couche

Chacune livrable et testable seule, dans l'ordre.

- api :
  1. **Recherche** : `common.search.normalize()` et `match()`, vecteurs de test JSON partagés, tests.
  2. **`catalog`** : `Trade`, `Service`, contraintes, `RESERVED_TRADE_SLUGS`, services d'écriture, `active_trades()`, admin modifiable (inline, sans suppression, slug figé), groupe `Saisie catalogue` par migration, fabriques, tests.
  3. **`zones`** : `City`, `Zone`, M2M `trades`, services, `zones_for_point`, `resolve_zone_text`, `availability`, admin GIS, permissions du groupe, fabriques, tests PostGIS (dont le chevauchement).
  4. **API publique en lecture** : 4 vues, `LocalizedText`, `catalog_read`, cache et `ETag`, `REFERENCE_LIST_MAX`, codes d'erreur i18n, tests (anonyme, avec jeton, inactif, inconnu, 405, 304).
  5. **Données de départ** : `seed_reference_data` et son module (tableaux ci-dessus), cible `make seed`, tests d'idempotence.
  6. **Contrat et documentation** : `make openapi`. ARCHITECTURE.md : zones en centre + rayon, polygone optionnel ; admin modifiable pour `catalog` et `zones`. `apps/api/CLAUDE.md` : slug comme identifiant public des données de référence. Règle « jamais d'icône seule » dans DESIGN.md. ADR 0009 accepté après validation.
- packages/api-client :
  1. `src/search/` : `normalizeSearch()` et `matchSearch()`, écrits à la main hors du code généré, testés sur les vecteurs de l'api 1.
- web / console :
  1. _(optionnelle)_ **web — métiers sur l'accueil** : Server Component, revalidation 5 min, libellé `name[locale] ?? name.fr`, pictogramme toujours accompagné de son libellé, aucune chaîne en dur, revue design. Exige un appel serveur **sans cookie ni jeton** (variante publique dans `lib/bff.ts`, relue par `security-reviewer`).
  - console : rien (la saisie passe par l'admin Django).
- client / pro : rien dans cette spec (étape 6). Le client TS régénéré et `src/search/` suffisent.

## Questions à trancher (Zay)

Les six propositions sont acceptées par la revue terrain. Il reste à les confirmer.

1. **Q1 — Slugs des métiers (URL SEO, figés ensuite).** Proposition : `plombier`, `electricien`, `climatisation`, `electromenager`, `menage`, `petits-travaux`.
   _Terrain : accepté._ Réserve : `menage` est gardé, avec le H1 et le titre SEO « Femme de ménage et nettoyage ». Un slug changé plus tard passe par une redirection 301 (étape SEO).
2. **Q2 — Frigo et congélateur dans froid et clim** (ce sont les frigoristes qui les réparent).
   _Terrain : accepté._ Réserve : « frigo » est aussi un alias d'électroménager. La recherche montre les deux métiers et le client choisit.
3. **Q3 — Prix de référence.** Proposition : un seul `price_from_xof`, vide au lancement, affiché seulement quand l'Ops l'a saisi.
   _Terrain : accepté._ Réserves intégrées : jamais de fourchette min-max ; mention en toutes lettres « prix de départ, le prix final est dans le devis » ; jamais transmis à l'IA pour être restitué au client.
4. **Q4 — Ouverture d'un métier dans une zone : explicite** (case cochée), avec une action « Ouvrir partout ».
   _Terrain : accepté._ Réserve intégrée : un quartier hors liste ne bloque jamais le client (texte libre, `zone_unknown`, demande acceptée).
5. **Q5 — Grain de la banlieue et liste des 24 zones.** Proposition : une zone par commune pour Pikine, Guédiawaye, Keur Massar et Rufisque, avec les alias de quartier du tableau. Gorée reste hors du seed V1.
   _Terrain : accepté._ Réserves intégrées : si un point tombe dans plusieurs cercles, le client choisit ; `boundary` approximatif optionnel. À trancher : Gorée hors V1, d'accord ?
6. **Q6 — Qui saisit dans l'admin.** Proposition : toi seul au départ, avec ton compte technique. Une personne Ops éventuelle aurait un compte technique distinct de son compte Ops, le groupe `Saisie catalogue` et un TOTP admin ; une petite commande auditée serait alors ajoutée à la tâche api 2.
   _Terrain : accepté, sans réserve._
