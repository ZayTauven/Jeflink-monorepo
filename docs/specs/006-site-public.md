# Spec 006 — Site public : accueil, métiers, pages métier × quartier

Statut : api et web livrés le 2026-10-05 (api 1-6, web 1-12), revues `security-reviewer` et `design-guardian` faites ; web 13 en partie (copie à valider par Zay, mesures Lighthouse à faire), web 14 en attente de Q2 ; docs 1 fait · validée par Zay le 2026-10-05, recommandations retenues sur Q1 à Q15 (Q2, Q7, Q8, Q9, Q14 et Q15 restent à compléter avant `SITE_INDEXABLE=true`, pas avant le dev) · ADR lié : 0013 (rendu du site public et URL des langues, accepté) · Revue `terrain-reviewer` faite le 2026-10-05 (voir « Revue terrain et arbitrages »)

## Problème

Awa cherche « plombier Ouakam » sur Google depuis un Android d'entrée de gamme. Moussa, à Milan, transfère un lien dans le groupe WhatsApp de la famille. Ibou, électricien, a entendu parler de Jeflink et veut savoir comment y entrer.

Aujourd'hui, `apps/web` n'a qu'un accueil provisoire (un titre et une phrase). Aucune page n'est trouvable, aucune ne s'affiche proprement quand on la partage, et le parcours de demande (spec 003) n'a pas de porte d'entrée. PRODUCT.md §6 classe le SEO métier × quartier en V1 (impact fort, effort faible). C'est l'étape 6 de `chantier-prod.md`.

Cette spec livre le site public, en direction Crafto « marketing-strategy » :

- l'accueil, la liste des métiers, une page par métier ;
- les pages `/[metier]/[quartier]`, générées depuis catalog × zones, et une recherche de quartier sans JS ;
- les pages À propos, Contact et Devenir pro ;
- le SEO (métadonnées, sitemap, robots, JSON-LD, Open Graph) ;
- les images de la banque, optimisées.

Elle ne promet rien que la V1 ne tient pas.

| Zone sensible        | Touchée ? | Détail                                                                                                                                                                                                                                                                               |
| -------------------- | --------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Argent               | Non       | Prix « à partir de » saisis par l'Ops, en entier XOF (`formatXof`), toujours suivis de `catalog.priceNotice`. Aucun mouvement, aucun `LedgerEntry`.                                                                                                                                  |
| KYC                  | Non       | Aucune pièce, aucun selfie. Mais le site dit ce que veut dire « Pro vérifié » : le texte doit coller à la procédure réelle (Q7). Le site n'est pas indexable tant que cette procédure n'est pas écrite.                                                                              |
| Machine à états      | Non       | Aucune transition. `/api/stats/` compte des réservations `closed`, en lecture seule, par un sélecteur de `bookings`.                                                                                                                                                                 |
| Auth, permissions    | Oui, peu  | Nouvel accès public du BFF à l'API (`publicApi()`) : sans cookie, sans jeton, sans en-tête du visiteur, `GET` sur une liste fermée de chemins (web 2, [sécu]). Les pages publiques ne lisent jamais la session.                                                                      |
| Données personnelles | Peu       | Pas de formulaire (Q4). Agrégats publics bornés par des seuils : aucun pro n'est isolable. Le numéro du support publié est un numéro de service (Q8). Un texte Ops qui contient un numéro est refusé. Le texte tapé dans la recherche de quartier n'est ni enregistré ni journalisé. |

## Parcours

- **Client venu de Google (Awa).** Sur `/plombier/ouakam` :
  - le titre « Plombier à Ouakam » et ce que fait le métier (services, « à partir de ») ;
  - comment ça marche, en 3 étapes, et ce que Jeflink garantit aujourd'hui ;
  - quand le pro vient, d'après les règles réelles (devis avec un créneau, votre choix, confirmation du pro) ;
  - les autres métiers ouverts à Ouakam, et le plombier dans les quartiers voisins ;
  - deux boutons, visibles sans défilement et repris dans une barre fixe en bas de l'écran sur mobile :
    - « Faire une demande » mène à `/demande?metier=plombier&quartier=ouakam`, avec la mention « Un code SMS vous sera envoyé pour vous connecter. » (spec 001), puis au formulaire pré-rempli ;
    - « Écrire sur WhatsApp » ouvre un message prérempli avec des amorces à compléter (voir « Message WhatsApp ») ;
  - un lien « C'est urgent ? » qui mène à `/demande?…&urgence=1` ou à WhatsApp.
- **Client qui dit son quartier avec ses mots.** Sur `/[metier]` et sur la 404, un champ « Votre quartier » (formulaire `GET`, sans JS) envoie vers `/recherche`. Trois issues :
  - « Parcelles » ou « PA » mène à la page du quartier ;
  - « Sacré » propose « Sacré-Cœur » ;
  - « Gorée » propose « Pas de page pour ce quartier ? Dites-nous où vous êtes sur WhatsApp ».
    Jamais de cul-de-sac.
- **Client venu de l'accueil.** Il choisit un métier (puces ou cartes), puis son quartier dans la liste ou par le champ. Il peut aussi passer par `/demande` (« Autre quartier », specs 002 et 003).
- **Pour un proche, ou depuis l'étranger.**
  - Un client de Dakar peut faire la demande pour le logement d'un proche : il écrit le repère du proche, puis lui transmet le code de fin par WhatsApp (« Partager à un proche », spec 004).
  - Depuis l'étranger, la connexion n'accepte que les numéros du Sénégal en V1 (spec 001, Q1). La FAQ oriente vers un proche à Dakar ou vers WhatsApp.
- **Partage sur WhatsApp (Moussa).** Le lien d'une page montre un aperçu : titre, description en deux lignes au plus, et l'image Open Graph de la page.
- **Artisan (Ibou).** `/devenir-pro` dit en peu de mots :
  - ce que Jeflink lui apporte et ce qu'on vérifie ;
  - ce que ça coûte : pas de frais d'entrée ni d'abonnement, une commission sur chaque mission terminée, au taux affiché avant chaque devis (spec 005) ;
  - comment entrer : « Envoyez-nous un message vocal sur WhatsApp » (bouton « Je veux rejoindre Jeflink »).
    Pas d'inscription en ligne : elle viendra avec l'app Pro.
- **Ops (admin Django, groupe `Saisie catalogue`).**
  - Saisit, pour chaque quartier, un texte d'intro et sa forme grammaticale (« au Plateau », « aux Almadies »), et pour chaque métier un texte d'intro.
  - Complète les alias des quartiers et des métiers avec les mots dits par les gens.
  - Ouvre ou ferme un métier dans un quartier. Le site suit en 5 minutes au plus (cache).
- **Zay.** Valide la copie `fr` (i18n). Le wolof écrit vient seulement d'un locuteur nommé (Q2).

## Réalité terrain

- **Réseau et téléphones.**
  - Un budget par page, mesuré sur deux profils, 3G rapide et 3G lente (voir « Performance »). Une seule image lourde par vue, en AVIF ou WebP, avec des `srcset` et `sizes` justes.
  - Ni vidéo, ni bibliothèque d'animation, ni carrousel en JS. Deux îlots JS en tout : le menu mobile et la pause du bandeau.
  - Les pages se lisent et s'utilisent sans JS : recherche de quartier en `GET`, barre d'actions en CSS, menu replié sur les liens du pied de page.
- **Langues.**
  - Les recherches s'écrivent en français (« plombier Parcelles ») ; le wolof est surtout parlé. En V1, les pages publiques sont en français, et la structure est prête pour `/wo/…` (ADR 0013).
  - Si un locuteur l'a validé (Q2), un bandeau court en wolof dès la V1, sur l'accueil et `/devenir-pro`. Le bouton « Je préfère en wolof » ouvre WhatsApp, où le support répond en wolof.
  - Copie en phrases courtes (12 mots au plus), aucun terme juridique sans exemple.
  - Les quartiers sont des noms propres : la grammaire (« à Ouakam », « au Plateau », « aux Almadies », « à la Médina ») est une donnée (`Zone.locative_fr`), pas une règle en code.
- **Adressage.** Les gens disent « Parcelles », « Yoff Virage », « Sacré-Cœur 3 ». La recherche de quartier s'appuie sur les alias des zones (spec 002, `matchSearch`) ; les compléter est un travail de données, pas de code. Le site ne demande aucune position. Le repère se saisit dans `/demande` ou s'écrit sur WhatsApp.
- **Confiance.**
  - Aucun chiffre inventé, aucun témoignage, aucun logo de partenaire ou de média, aucune photo présentée comme un vrai pro ou un vrai client.
  - Les preuves chiffrées n'apparaissent qu'au-delà de seuils réels (`/api/stats/`).
  - « Travail garanti » s'explique par ce que la V1 fait vraiment (Q6) : pas de « satisfait ou remboursé ».
  - « Ce que Jeflink ne vous demande jamais » : de l'argent, votre code de connexion, ou de payer plus que le prix accepté.
  - Contre l'usurpation : la FAQ « Comment savoir que c'est bien Jeflink ? » ; sur chaque page, le numéro du support, ses horaires et le nom de la société, en pied de page.
- **Prix.** La mention `catalog.priceNotice` dit exactement « Prix de départ, le prix final est dans le devis. » (`fr.json`). Elle ne dit pas qui valide le prix. Le site y ajoute, sans toucher à la clé (spec 002, DESIGN.md), « Vous choisissez le devis. Le prix ne change jamais sans votre accord. » C'est la règle de l'avenant : refusé, le travail continue au prix accepté (spec 004).
- **Paiement.** « Vous réglez le pro directement, en espèces ou par mobile money. Jeflink ne vous facture rien. » Aucun nom ni logo de moyen de paiement : aucun paiement n'est intégré en V1 (DESIGN.md › Banque d'images). Le moment du paiement (à la fin ? un acompte est-il permis ?) n'est fixé par aucune spec : le site n'en dit rien tant que Q14 n'est pas tranchée.
- **Délai.**
  - Aucune promesse de délai. On dit les règles réelles : les pros proposent un créneau dans leur devis, vous choisissez, le pro confirme sous 4 h (1 h si c'est urgent), sans compter la nuit (spec 003). Les valeurs viennent de `rules`.
  - « C'est urgent » existe dans la demande (spec 003) : les pros la voient en premier.
- **WhatsApp d'abord.** Le bouton WhatsApp est au même rang que la demande, avec un message prérempli sans donnée personnelle. Les aperçus de lien sont soignés (Open Graph léger).
- **Connexion avant la demande.**
  - `/demande` exige une session (spec 003) : le code SMS passe avant le formulaire. C'est une friction connue sur un réseau lent.
  - La page de connexion a déjà « Je ne reçois pas le code », avec un lien WhatsApp toujours visible (spec 001). Le site prévient avant le clic (« Un code SMS vous sera envoyé »), et WhatsApp reste l'autre voie (Q12).

## Modèle de données et API

### Plan du site

| Route                                          | Contenu                                                                                 | Indexée                                 | Données (via `publicApi()`, cache 5 min)                                           |
| ---------------------------------------------- | --------------------------------------------------------------------------------------- | --------------------------------------- | ---------------------------------------------------------------------------------- |
| `/`                                            | Accueil                                                                                 | oui                                     | `catalog/trades/`, `zones/`, `stats/`                                              |
| `/metiers`                                     | Tous les métiers (page sœur « services » de Crafto)                                     | oui                                     | `catalog/trades/`                                                                  |
| `/[metier]`                                    | Page métier : services, prix, quartiers ouverts, champ « Votre quartier »               | oui                                     | `catalog/trades/{slug}/`, `zones/`, `stats/?trade=`                                |
| `/[metier]/[quartier]`                         | Page métier × quartier                                                                  | si `indexable`, sinon `noindex, follow` | `catalog/trades/{slug}/`, `zones/{slug}/?trade=`, `zones/{slug}/trades/`, `stats/` |
| `/recherche?metier=&quartier=`                 | Résultat de la recherche de quartier : redirection, suggestions, ou WhatsApp            | non (`noindex`)                         | `zones/`, `catalog/trades/{slug}/`                                                 |
| `/a-propos`                                    | Pourquoi Jeflink, ce qu'on vérifie, Dakar                                               | oui                                     | `stats/` (seuils)                                                                  |
| `/contact`                                     | WhatsApp, appel, horaires                                                               | oui                                     | configuration serveur                                                              |
| `/devenir-pro`                                 | Recrutement des pros, par WhatsApp (Q10)                                                | oui                                     | configuration serveur                                                              |
| `/demande?metier=&quartier=&service=&urgence=` | Existant (spec 003), pré-rempli (web 9)                                                 | non (déjà `noindex`)                    | inchangé                                                                           |
| `/robots.txt`, `/sitemap.xml`, images OG       | Fichiers de métadonnées de Next                                                         | sans objet                              | `catalog/coverage/`                                                                |
| 404 globale, 404 de métier, erreur publique    | Utiles : champ « Votre quartier », liens vers les métiers (si le cache les a), WhatsApp | non                                     | `catalog/trades/` (facultatif)                                                     |

**Règles d'URL**

- **Une seule forme** : minuscules, sans barre finale. `src/proxy.ts` redirige déjà la barre finale. Il redirige aussi en 308 un chemin de page qui contient une majuscule (« /Plombier/Ouakam », fréquent depuis un clavier de téléphone) ; la requête et `/api` ne sont pas touchées.
- **Alias** : `/plomberie` ou `/plombier/parcelles` redirigent en 307 vers le slug, seulement si le mot est **égal** à un alias (rang 0 de `matchSearch`), jamais sur un préfixe. Le 307 s'explique par le fait que les alias sont modifiables par l'Ops. Ces URL ne vont jamais dans le sitemap.
- **`/wo/…`** n'est pas servi en V1 (404). `wo`, `fr` et `en` sont réservés dès maintenant (ADR 0013).
- **Slugs réservés** : `RESERVED_TRADE_SLUGS` devient un fichier JSON unique, lu par Django et vérifié par un test du web (api 1). On y ajoute `fr`, `wo`, `en`, `og`, `opengraph-image`, `twitter-image`, `icon`, `apple-icon`, `manifest`, `sitemap`, `robots`, `garantie`, `tarifs`, `comment-ca-marche`, `services`, `merci`, `hors-ligne`. `recherche` y figure déjà. Pour les zones (second segment) : `opengraph-image`, `twitter-image`.

### Recherche de quartier (`/recherche`)

- Formulaire `GET` sur `/[metier]` et sur les 404 : `metier` (slug, caché) et `quartier` (texte, 40 caractères au plus). Le résultat est rendu par le serveur, sans JS.
- Le serveur applique `matchSearch` (`@jeflink/api-client/search`, mêmes règles que l'API et l'app) aux zones en cache où le métier est ouvert :
  - **une égalité** (« PA », « Parcelles ») : redirection 307 vers `/[metier]/[quartier]` ;
  - **des préfixes** (« Sacré », « Grand ») : liste des quartiers proposés, en liens ;
  - **une zone connue où le métier n'est pas ouvert** : « Pas encore de plombier à Rufisque », et les autres métiers ouverts dans ce quartier ;
  - **rien** : « Pas de page pour ce quartier ? Dites-nous où vous êtes sur WhatsApp », et le lien vers `/demande` (« Autre quartier »).
- Le texte tapé ne sort pas de la requête. Il n'est ni enregistré, ni journalisé par l'application, ni recopié dans le message WhatsApp (il pourrait contenir une adresse ou un numéro). La page est `noindex`.
- Les alias de zones font la qualité de cette recherche : c'est un travail de l'Ops (tâche « données »), vérifié par un critère d'acceptation.

### Message WhatsApp

- Construit par une fonction pure (`whatsappUrl`, existante), à partir de clés i18n. Il ne contient aucune donnée personnelle : seulement le métier et le quartier de la page.
- Forme (à valider) : « Bonjour, j'ai besoin d'un plombier à Ouakam. » puis, à la ligne, les amorces « Problème : … » et « Mon repère : … ».
- Variante « Je préfère en wolof » : « Bonjour, je préfère échanger en wolof. » suivi des mêmes amorces. Le texte prérempli reste en français : nous n'écrivons pas de wolof (Q2), le support répond en wolof (Q8).
- Test : encodage correct des caractères accentués et wolof (`é`, `è`, `ç`, `ŋ`, `ë`) et des sauts de ligne ; aucune valeur d'un utilisateur dans l'URL produite.

### Pages métier × quartier

- **Existence.**
  - Une page répond si le métier est actif, la zone et sa ville actives, et le métier ouvert dans la zone (`availability` = `available`, spec 002). Sinon, c'est la 404 utile, jamais une page vide.
  - C'est l'interrupteur de l'Ops : une fermeture fait disparaître la page et sa ligne du sitemap en 5 minutes au plus, une réouverture la fait revenir. On répond 404 et non 410, puisque c'est réversible.
- **Rendu.** À la requête (CSP à nonce, ADR 0013), avec les données en cache 5 minutes. Pas de `generateStaticParams` ni d'ISR en V1. Les paramètres sont validés contre le catalogue en cache avant tout appel de détail : un slug inconnu ne coûte aucun appel.
- **Une erreur de l'API n'est pas une 404.**
  - Si l'API ne répond pas, la dernière copie du cache sert la page.
  - Sans copie, on affiche la page d'erreur (500) avec WhatsApp. Jamais `notFound()`, qui ferait désindexer la page.
  - `notFound()` ne sert que sur `trade_not_found`, `zone_not_found` ou une paire non ouverte.
- **Ce qui varie vraiment d'un quartier à l'autre :**
  1. Le titre : `{seo_title} {locatif}`, par exemple « Plombier à Ouakam », « Femme de ménage et nettoyage aux Almadies ». Sans locatif saisi, le repli est « à {nom} » (clé i18n).
  2. Le texte d'intro du quartier (`Zone.seo_intro`, écrit par l'Ops en français parlé : repères connus, sous-quartiers, particularités du bâti ou du réseau d'eau).
  3. Les quartiers voisins où le métier est ouvert, 4 au plus, triés par distance entre les centres (PostGIS), en liens.
  4. Les autres métiers ouverts dans ce quartier, en liens.
  5. Les chiffres du métier dans le quartier, au-dessus des seuils seulement.

  Ce qui est commun à toutes les pages d'un métier :
  - services et prix, texte d'intro du métier ;
  - comment ça marche, « Quand le pro vient-il ? », garanties ;
  - FAQ courte, horaires de réponse du support.

- **Anti-contenu dupliqué.**
  - Une page est indexable si son quartier a un texte d'intro (`indexable`, calculé par l'API dans `coverage` et dans le détail de la zone).
  - Sinon, elle porte `noindex, follow`, sort du sitemap, et son canonical pointe vers elle-même. Jamais vers la page du métier : les contenus diffèrent.
  - L'Ops rend la page indexable en saisissant le texte (Q3).
- **Données affichées.**
  - Le prix « à partir de » est donné par service, jamais par métier (spec 002). Il est toujours suivi de `catalog.priceNotice` et de la phrase sur l'accord du client.
  - Le nombre de pros vérifiés qui couvrent le métier dans le quartier n'apparaît qu'à partir de 3. Jamais de nom, de photo ni de note individuelle.
  - Pas de « disponible maintenant » : on ne le sait pas.
- **Barre d'actions mobile.** « Faire une demande » et « WhatsApp » restent fixés en bas de l'écran, en CSS seul, sur les pages métier, métier × quartier et l'accueil :
  - zone de sécurité (`env(safe-area-inset-bottom)`), et un `scroll-padding-bottom` pour ne jamais masquer l'élément qui a le focus (WCAG 2.4.11) ;
  - masquée sur grand écran.
- **Lien de demande.** `/demande?metier=<slug>&quartier=<slug>`, plus `&service=<slug>` depuis la ligne d'un service, et `&urgence=1` depuis « C'est urgent ? ». Le formulaire reprend ces valeurs si le catalogue les connaît, et les ignore sans bruit sinon (web 9).

### Accès public à l'API depuis le web

- **`publicApi()`** (web 2, [sécu]) :
  - `GET` seulement, sur une liste fermée de préfixes : `/api/catalog/`, `/api/zones/`, `/api/stats/` ;
  - aucun cookie, ni `Authorization`, ni `X-Jeflink-Client-Ip`, ni `X-Install-Id`, et aucune lecture de `headers()` ou de `cookies()` ;
  - liste fermée d'en-têtes, à valider par `security-reviewer` (l'API identifie l'appelant comme le serveur Next, et la limite `catalog_read` s'y applique).
- **Cache de données de Next** : revalidation 300 s, étiquettes `catalog`, `zones` et `stats`, une seule entrée pour tous les visiteurs. Si l'API échoue, la dernière copie est servie.
- **Séparation** : `serverApi()` et `serverApiWithSession()` restent réservés aux pages avec session. Un test d'architecture interdit leur import sous `app/(site)`.

### Endpoints

Tous `AllowAny`, `GET` seulement, sur le socle `PublicReferenceView` : limite `catalog_read`, `Cache-Control` public et `ETag`. Les fronts appellent sans jeton (spec 002). Ni position, ni rayon, ni polygone dans les réponses.

| Méthode | Chemin                        | Statut                    | Réponse                                                                                                                                                                                                                |
| ------- | ----------------------------- | ------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| GET     | `/api/zones/{slug}/`          | nouveau                   | `{slug, name, city, aliases, locative: LocalizedText \| null, intro: LocalizedText \| null, indexable, nearby[{slug, name}]}`. `?trade=<slug>` limite `nearby` aux zones où ce métier est ouvert. `404 zone_not_found` |
| GET     | `/api/catalog/coverage/`      | nouveau                   | `[{trade, zone, indexable, updated_at}]` : paires ouvertes (métier actif, zone et ville actives). Borne `COVERAGE_LIST_MAX` (5 000, test), sans pagination                                                             |
| GET     | `/api/stats/`                 | nouveau (tag `analytics`) | `{missions_completed, rating, verified_pros, rules}`. Filtres `?trade=`, `?zone=`. `404 trade_not_found`, `zone_not_found`                                                                                             |
| GET     | `/api/catalog/trades/{slug}/` | modifié                   | ajoute `seo_intro: LocalizedText \| null`                                                                                                                                                                              |

**`/api/stats/`** (`analytics.selectors.public_stats(trade=None, zone=None)`, qui lit les sélecteurs de `bookings`, `reviews` et `providers` sans rien écrire) :

- `missions_completed` : réservations `closed`, hors pros `is_demo` et comptes de revue ; filtrées par métier et par zone de la demande. Arrondies à la dizaine inférieure, `null` sous `PUBLIC_STATS_MIN_MISSIONS` (50).
- `rating` : `{average, count}` sur `reviews.selectors.counted_reviews()`. `null` sous `PUBLIC_STATS_MIN_REVIEWS` (20). Une requête filtrée renvoie aussi `null` si moins de 3 pros distincts sont notés : on ne doit jamais pouvoir lire la note d'un seul artisan.
- `verified_pros` : fiches `verified` hors `is_demo`, filtrées par métier et par zone de la fiche. Valeur exacte de 3 à 9, arrondie à la dizaine au-delà (le web affiche « plus de 20 »). `null` sous `PUBLIC_STATS_MIN_PROS` (5 sans filtre, 3 avec filtre).
- `rules` : lus dans les réglages existants des specs 003 et 004 (`BOOKING_CONFIRM_TTL` et sa variante urgente, fenêtre de contestation, nombre de devis). Le site ne recopie jamais ces valeurs dans sa copie.
  - `max_quotes_per_request` ;
  - `dispute_window_hours` ;
  - `pro_confirm_hours` et `pro_confirm_hours_urgent` ;
  - `quiet_hours` (`{start, end}`, heure de Dakar).
- Les seuils sont des réglages (`settings`), jamais en dur (Q5).

### Modèles modifiés

| Modèle          | Ajout                                                                                                                                                     |
| --------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `catalog.Trade` | `seo_intro_fr` / `seo_intro_wo` (600, optionnels) : texte de la page métier                                                                               |
| `zones.Zone`    | `locative_fr` / `locative_wo` (90, optionnels : « aux Almadies ») · `seo_intro_fr` / `seo_intro_wo` (600, optionnels) : texte des pages métier × quartier |

- Migrations additives, valeur vide par défaut. Saisie dans les formulaires d'admin existants (groupe `Saisie catalogue`), avec un filtre « intro vide ».
- **Validation** (`clean()` et services) :
  - un texte qui contient un numéro de téléphone (motifs de `common.pii`) ou une URL est refusé : il serait publié tel quel ;
  - `locative_fr` doit contenir le nom de la zone (pas de « à Ouakam » sur la fiche de Ngor).
- `indexable` = `seo_intro_fr` non vide, calculé dans `zones.selectors` (une seule règle pour le détail et `coverage`).
- Les alias (`aliases`, spec 002) ne changent pas de forme : seul leur contenu est complété par l'Ops.

### Transitions de réservation touchées

Aucune.

### SEO

- **Métadonnées** (`generateMetadata`) :
  - titre de 60 caractères au plus (`{H1} · Jeflink`) ;
  - description de 155 caractères au plus, composée à partir d'une clé i18n (métier, locatif, « jusqu'à 3 devis, vous choisissez ») ;
  - `og:description` de 100 caractères au plus, pour tenir en deux lignes dans l'aperçu WhatsApp ;
  - `metadataBase` = `SITE_URL` (nouvelle variable serveur), canonical absolu sur chaque page ;
  - `og:locale` `fr_SN`, `og:site_name` Jeflink.
- **hreflang** : aucun en V1, puisqu'il n'y a qu'une langue (le bandeau wolof ne fait pas une page wolof). Avec le `wo` : `fr`, `wo` et `x-default` vers `fr` (ADR 0013).
- **`sitemap.xml`** (`app/sitemap.ts`) : pages fixes, métiers et paires `indexable`, avec `lastModified` = `updated_at`. Jamais `/recherche`.
- **`robots.txt`** (`app/robots.ts`) : `Disallow` sur `/compte`, `/demande`, `/connexion`, `/recherche` et `/api`, et lien vers le sitemap. Si `SITE_INDEXABLE` n'est pas vrai (défaut, en local et en staging) : tout est interdit, et un `noindex` global est posé.
- **`SITE_INDEXABLE=true` exige** (contrôle au démarrage, `lib/site-config.ts`) `SITE_URL`, `SUPPORT_WHATSAPP_NUMBER`, `SUPPORT_PHONE_NUMBER` et `SITE_LEGAL_NAME`. Ce qui ne se vérifie pas en code va dans `chantier-prod.md`, comme condition de passage : procédure « Pro vérifié » écrite dans `docs/ops/` (Q7), licences des images (Q9), intros saisies (Q3).
- **JSON-LD** (texte échappé selon la doc embarquée de Next ; vérifier qu'aucune violation de CSP n'apparaît) :
  - accueil : `Organization` et `WebSite` ;
  - métier et métier × quartier : `Service` (`serviceType` ; `provider` = l'Organization ; `areaServed` = la `Place` du quartier, contenue dans Dakar ; `offers.priceSpecification.minPrice` en XOF, seulement si un prix est saisi) et `BreadcrumbList`.
  - Pas de `LocalBusiness` : aucune adresse ouverte au public par quartier (Q11). Pas d'`AggregateRating` : avis sur soi-même non éligibles, et chiffres sous seuil. Pas de `FAQPage`.
- **Open Graph** : une image par page métier et métier × quartier (`opengraph-image.tsx`, `next/og`), en 1 200 × 630. Elle porte le titre et le logo sur un aplat `sand` ou `ink`, sans photo, et pèse 100 ko au plus. Une image par défaut sert les autres pages. Les polices sont des fichiers OFL versionnés dans l'app.

### Contenu et i18n

- **Où vivent les chaînes.** Toutes dans `messages/fr.json`, espace `site` : `nav`, `home`, `trade`, `tradeZone`, `search`, `whatsapp`, `about`, `contact`, `pro`, `faq`, `footer`, `seo`, `notFound`. Le bandeau wolof (web 14) a sa clé `site.woBanner`, rendue avec `lang="wo"`. `wo.json` reste vide : repli sur `fr`.
- **Ce qui part au navigateur.** Les pages publiques ne transmettent que les messages des îlots client (menu, bandeau). Sans précaution, `NextIntlClientProvider` v4 hérite de tout `fr.json`, soit environ 700 lignes de l'espace client à chaque page (test).
- **Ton.** Direct (skill `jeflink-design`), verbes d'action, montants en `25 000 F CFA`. Brouillon par l'agent (skills `copywriting`, `design:ux-copy` et `humanizer`), validation par Zay.
  - Phrases de 12 mots au plus dans `site.*` (contrôle automatique).
  - Aucun terme juridique ou technique sans exemple : « litige » devient « signaler un problème », « avenant » devient « le pro propose un nouveau prix ».
- **Formules interdites, car fausses en V1** (contrôle automatique sur `site.*`) :
  - « devis gratuit » : un devis « visite » peut être payant (spec 003) ;
  - « satisfait ou remboursé », « remboursement », « paiement sécurisé », « payez à la fin » (Q14) ;
  - « intervention en 30 min », « 24 h/24 » ;
  - les noms de moyens de paiement.
- **Exemples de ton** (à valider) :
  - titre de l'accueil : « Le bon pro, au bon prix, travail garanti. » ;
  - chapeau : « Des pros vérifiés à Dakar. Jusqu'à 3 devis, vous choisissez. » ;
  - étapes : « 01 Dites ce qui ne va pas » · « 02 Choisissez parmi 3 devis au plus » · « 03 Travail fini ? Donnez votre code au pro ». C'est le client qui donne le code de fin au pro (spec 004).
- **FAQ.** Chaque réponse s'appuie sur une règle des specs 001 à 005, citée dans un commentaire à côté de la clé :
  - **Combien ça coûte ?** Prix de départ, devis, prix qui ne change pas sans votre accord (specs 002, 003, 004).
  - **Comment je paie ?** Au pro, en espèces ou par mobile money ; Jeflink ne vous facture rien (specs 003, 005). Le moment du paiement attend Q14.
  - **Quand le pro vient-il ?** Créneau proposé dans le devis, votre choix, confirmation du pro sous `pro_confirm_hours` (spec 003).
  - **C'est urgent ?** Cochez « C'est urgent » : les pros voient votre demande en premier et confirment sous `pro_confirm_hours_urgent` (spec 003). Sinon, WhatsApp.
  - **Mon quartier n'est pas dans la liste ?** « Autre quartier » ou WhatsApp (specs 002, 003).
  - **Le pro ne vient pas ?** Appelez-le, puis « Le pro n'est pas venu » ; votre demande revient vers les pros (spec 004).
  - **Un problème après le travail ?** `dispute_window_hours` pour le signaler, Jeflink examine (spec 004).
  - **Comment savoir que c'est bien Jeflink ?**
    - Jeflink ne vous demande jamais votre code de connexion, même au téléphone : le SMS le dit (« Ne le donnez à personne, ni à un artisan, ni à Jeflink », spec 001).
    - Jeflink ne vous demande jamais d'argent.
    - Le code de fin, vous le donnez au pro seulement quand le travail vous convient.
    - Nos seuls numéros sont en bas de cette page.
  - **Vous commandez pour un proche ?** Faites la demande avec son repère, puis partagez-lui le code de fin par WhatsApp (spec 004).
  - **Vous êtes à l'étranger ?** Un proche à Dakar fait la demande avec son numéro, ou écrivez-nous sur WhatsApp (spec 001, Q1).
  - **Je parle wolof.** Écrivez-nous sur WhatsApp, nous répondons en wolof (Q8).
  - **Que veut dire « Pro vérifié » ?** La liste de Q7, rien de plus.
- **Textes de données** (intros, locatifs) : saisis par l'Ops dans l'admin, `fr` d'abord, en français parlé avec des repères connus, relus par un habitant du quartier (Q3). Le `wo` vient d'un locuteur validé (ADR 0009 ; spec 001, Q12).

### Accueil : ce qu'on prend à Crafto, section par section

Référence : `references/crafto/demo-marketing-strategy.html` et `demos/marketing-strategy/marketing-strategy.css`. On reprend la composition, les proportions et le rythme, jamais le HTML, le JS ni les plugins (anime.js, Swiper, skrollr, curseur). Le rayon de Crafto (20 px) devient `--jf-radius` (10 px) : aucune autre valeur.

| #   | Section Crafto                                                                    | Décision          | Version Jeflink                                                                                                                                                                                                                                                                                                            |
| --- | --------------------------------------------------------------------------------- | ----------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | En-tête transparent, bouton pilule « Get in touch », menu plein écran fond narvik | Adapter           | Logo, liens (Métiers, Comment ça marche, À propos, Contact), « Mon espace » (toujours le même lien, aucune lecture de session), pilule « Faire une demande ». Mobile : bouton « Menu », un lien vers le pied de page sans JS, qui ouvre un `<dialog>` plein écran `sand` avec JS.                                          |
| 2   | Hero : vidéo en autoplay, titre géant, stat « 95 % », texte, CTA, badges de notes | Adapter           | Titre géant Funnel Display, chapeau, CTA double visible sans défilement sur mobile, **image** forte (LCP préchargée) à la place de la vidéo, puces des métiers (liens, données), bandeau wolof si Q2. Stat « 95 % » et badges écartés (faux, logos tiers).                                                                 |
| 3   | Deux cartes : image avec bouton vidéo · carte blanche (pastille, titre, CTA)      | Adapter           | Carte image (scène de métier, sans bouton vidéo) et carte « Ce que Jeflink garantit aujourd'hui » (pastille, titre, lien vers À propos).                                                                                                                                                                                   |
| 4   | « About our agency » : texte et 3 gros chiffres (98 %, 125+, 186+)                | Adapter           | 3 gros chiffres **vrais par construction** : `rules` (« 3 devis au plus », « 48 h pour signaler un problème ») et « 0 F de frais Jeflink pour vous ». Les preuves réelles (`stats`) remplacent un chiffre au-delà des seuils.                                                                                              |
| 5   | Cartes empilées plein écran avec parallaxe                                        | Adapter           | Grille des métiers en cartes à grandes images arrondies (données), image chargée à la demande. Ni parallaxe ni empilement.                                                                                                                                                                                                 |
| 6   | Bandeau défilant géant (Swiper en autoplay)                                       | Garder (CSS)      | Noms des métiers (données) en Funnel Display, animation CSS, bouton « Mettre en pause » (WCAG 2.2.2), arrêt au survol et au focus, statique avec `prefers-reduced-motion`. Copie doublée en `aria-hidden`.                                                                                                                 |
| 7   | Sections numérotées 01, 02, 03, image collante, badge qui tourne                  | Garder            | « Comment ça marche » en 3 étapes, suivi de « Quand le pro vient-il ? » ; image `sticky` en CSS sur grand écran, empilée sur mobile. Pas de sections en `100vh`, pas de badge qui tourne.                                                                                                                                  |
| 8   | Phrase centrée sur fond à motif, 2 CTA                                            | Adapter           | Bandeau final sur `sand` : une phrase et le CTA double. Fond à motif écarté (décoratif).                                                                                                                                                                                                                                   |
| 9   | Liste des prix (9X Awwwards…) en rangées                                          | Adapter le format | Deux listes en rangées bordées 1 px : « Ce que nous vérifions » (seulement la procédure réelle, Q7) et « Ce que Jeflink ne vous demande jamais ».                                                                                                                                                                          |
| 10  | « Meet our team » et 2 portraits                                                  | Écarter           | Remplacé par la carte « Vous êtes artisan ? » vers `/devenir-pro`, avec une scène de métier (aucun portrait présenté comme un pro).                                                                                                                                                                                        |
| 11  | FAQ en accordéon (Bootstrap)                                                      | Garder            | `<details>` et `<summary>` natifs, sans JS. Pas de JSON-LD `FAQPage`.                                                                                                                                                                                                                                                      |
| 12  | Rangée de logos clients                                                           | Écarter           | Aucun logo tiers, aucun moyen de paiement (rien d'intégré en V1).                                                                                                                                                                                                                                                          |
| 13  | Pied de page sombre : liens, e-mail géant, adresses, réseaux, grand logo          | Adapter           | Fond `ink` : liens vers toutes les pages et les métiers (suffisants sans JS), numéro du support en clair (WhatsApp et appel) et ses horaires, nom de la société (`SITE_LEGAL_NAME`), « Dakar » (aucune adresse inventée), grand logo SVG. Réseaux sociaux seulement s'ils existent. Liens légaux quand les pages existent. |
| —   | Curseur personnalisé, textes qui apparaissent au défilement, popup vidéo          | Écarter           | Animations sans fonction (DESIGN.md › Interdit).                                                                                                                                                                                                                                                                           |

S'y ajoute une section propre à Jeflink, entre 5 et 9 : **les quartiers couverts**. Ce sont les noms des zones (données), en texte, avec le champ « Votre quartier » et « Votre quartier n'y est pas ? Écrivez-nous ». Pas de carte interactive (trop lourde).

Ordre de l'accueil : 1, 2, 6, 7, 5, quartiers, 3 et 4 (garanties et chiffres), 9, 10, 11, 8, 13. Barre d'actions fixe en bas sur mobile. Règle de lisibilité : jamais de texte posé sur une photo. Le texte va sur un aplat, à côté de l'image ou dessous.

### Pages sœurs

| Page Crafto                              | Page Jeflink | Ce qu'on garde                                                                                                                                                                                                                                                       |
| ---------------------------------------- | ------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `demo-marketing-strategy-services.html`  | `/metiers`   | Titre de page en deux blocs (carte blanche avec pastille et titre, grande image) ; une carte par métier (pictogramme et libellé, description courte, lien). Les « process steps » réutilisent « Comment ça marche ».                                                 |
| `demo-marketing-strategy-about-us.html`  | `/a-propos`  | Titre en deux blocs, phrase centrée, rangées de points forts. Contenu : pourquoi Jeflink (prix connu avant, pros vérifiés, preuves), ce que nous vérifions, Dakar (photo de ville), CTA « Devenir pro ». Aucune photo d'équipe (`photos/equipes-projets/` interdit). |
| `demo-marketing-strategy-contact.html`   | `/contact`   | Titre en deux blocs. **Écartés** : témoignages et note « 4.58 » (faux), formulaire (Q4), carte Google Maps (tiers, lourd, CSP). Gardés : gros liens WhatsApp et appel, horaires, mention « Pour une intervention, faites une demande ».                              |
| `demo-marketing-strategy-portfolio.html` | aucune       | Écartée : pas de réalisations à montrer (plus tard, avec les photos de missions et le consentement : Passeport Pro, V3).                                                                                                                                             |

### Contact

Pas de formulaire en V1 (Q4). Un formulaire, ce serait une donnée personnelle de plus, un endpoint, de l'anti-spam et un traitement à déclarer, pour un besoin que WhatsApp couvre déjà.

- « Écrire sur WhatsApp » (`SUPPORT_WHATSAPP_NUMBER`, existant) et « Appeler » (`tel:`, nouvelle variable serveur `SUPPORT_PHONE_NUMBER`, facultative en local, exigée pour indexer).
- Sans numéro configuré, le bouton n'apparaît pas.
- Horaires du support : texte i18n validé par Zay (Q8), repris dans le pied de page de chaque page.
- Conformité : le support par WhatsApp et par téléphone est un traitement à inscrire au registre (`docs/compliance/registre-des-traitements.md`) s'il n'y est pas encore (docs 1). Aucune donnée n'est collectée par le site.

### États

| Situation                              | Comportement                                                                                                                                                                               |
| -------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Chargement                             | Rendu serveur complet. Pas de `loading.tsx` ni de squelette sur les pages publiques : le contenu est dans le premier HTML (SEO, 3G).                                                       |
| JS absent ou pas encore chargé         | Tout se lit et s'utilise : liens, recherche de quartier (`GET`), barre d'actions (CSS), FAQ (`<details>`). Le bouton « Menu » mène au pied de page.                                        |
| API indisponible, copie en cache       | Page servie depuis la copie (5 min, plus la durée de la panne).                                                                                                                            |
| API indisponible, aucune copie         | Accueil, À propos, Contact, Devenir pro : rendus quand même ; les sections de données (métiers, quartiers, chiffres) sont remplacées par le CTA WhatsApp. Pages métier : erreur 500 utile. |
| Catalogue vide ou chiffres sous seuil  | Section masquée, jamais un « 0 » ni un compteur vide.                                                                                                                                      |
| Métier, zone ou paire inconnu ou fermé | 404 utile : champ « Votre quartier », liens vers les métiers ouverts (depuis le cache), WhatsApp, accueil.                                                                                 |
| Hors ligne                             | Rien de propre au site en V1 (pas de service worker) : des pages légères suffisent. `/demande` garde son brouillon (spec 003).                                                             |

### Performance

| Page                    | JS initial (gz) | LCP en 3G rapide simulée | Poids de la première vue | Images                                        |
| ----------------------- | --------------- | ------------------------ | ------------------------ | --------------------------------------------- |
| Accueil                 | ≤ 120 ko        | < 2,5 s                  | ≤ 600 ko                 | hero ≤ 90 ko en 750 px, ≤ 180 ko en 1 600 px  |
| `/metiers`, `/[metier]` | ≤ 110 ko        | < 2,5 s                  | ≤ 450 ko                 | cartes ≤ 45 ko chacune, en chargement différé |
| `/[metier]/[quartier]`  | ≤ 100 ko        | < 2,5 s                  | ≤ 250 ko                 | un visuel de métier ≤ 40 ko sur mobile        |
| À propos, Contact, Pro  | ≤ 110 ko        | < 2,5 s                  | ≤ 400 ko                 | une image par page au plus                    |

- **Deux profils de mesure.** Lighthouse mobile en 3G rapide simulée (cible du tableau), et en 3G lente (400 kb/s, 400 ms de latence), sur `next build && next start` en local. Objectif en 3G lente : LCP de `/[metier]/[quartier]` sous 5 s. Les valeurs des deux profils sont notées dans la PR, et un vrai Android d'entrée de gamme est essayé une fois (web 13).
- **JS.** `Providers` (React Query, configuration du client) sort des pages publiques. Il ne sert qu'à l'espace client, qui passe dans son propre groupe de routes (web 1). Deux îlots client : menu mobile et pause du bandeau.
- **Pas de dépendance ajoutée** (règle 9) : ni anime.js, ni Swiper, ni GSAP, ni framer-motion, ni script tiers (mesure d'audience comprise).
- **Images.**
  - `next/image` partout, avec des `srcset` et `sizes` justes : un téléphone ne télécharge jamais la variante de bureau.
  - Image LCP préchargée (vérifier dans la doc embarquée de Next 16 le nom actuel de l'option, ex-`priority`) ; les autres en chargement différé.
  - Sources livrées en WebP aux tailles maximales affichées ; formats AVIF et WebP servis par Next (`images.formats`).
  - On ne lit pas l'en-tête `Save-Data` : les bonnes tailles suffisent, et la page reste la même pour tous (cache).
- **Polices.**
  - Celles du layout seulement (Funnel Display 600, Inter 400/500/600, `latin` et `latin-ext` pour `ŋ` et `ë`), aucun poids de plus.
  - `display: swap` (déjà posé), et un repli système ajusté pour le titre (`adjustFontFallback` de `next/font`, à vérifier dans la doc embarquée) : le titre se lit tout de suite, sans saut de mise en page.

### Accessibilité (AA)

- Lien « Aller au contenu », repères (`header`, `nav`, `main`, `footer`), un seul `h1` par page, titres dans l'ordre.
- Cibles de 48 px au moins, focus visible (anneau `accent-strong`), contraste AA (`accent` jamais en couleur de texte sur fond clair).
- Menu mobile : lien vers le pied de page sans JS, `<dialog>` natif avec JS (focus piégé, Échap ferme, focus rendu au bouton, `aria-expanded`).
- Barre d'actions fixe : ne masque jamais l'élément qui a le focus (`scroll-padding-bottom`, WCAG 2.4.11).
- Bandeau : bouton de pause, arrêt au survol et au focus, statique avec `prefers-reduced-motion`, copie doublée en `aria-hidden`. Les métiers restent atteignables en liens ailleurs sur la page.
- Bandeau wolof : `lang="wo"` sur l'élément.
- Pictogramme de métier toujours suivi de son libellé (spec 002). Images informatives avec un `alt` en i18n ; images décoratives en `alt=""`.
- Navigation au clavier complète, sans piège. FAQ en `<details>` natif. Champ « Votre quartier » avec un libellé visible et un exemple (« Parcelles, Yoff, Sacré-Cœur… »).

### Images de la banque (candidates)

Recherche dans `C:\Users\moham\Pictures\Banque\_catalogue\INDEX.tsv` et `catalogue.json`, vérification sur les planches-contact. **Le catalogue n'a pas de champ licence.** Le statut ci-dessous se déduit de `nom_origine` :

- `Jeflink-illustrations (N).jpg` : lot d'origine du projet, nom d'origine perdu, provenance probable d'une banque libre ;
- `Sn-Dahoo-Immobilier (N)` et `Biens-dahoo-archives (N)` : projet Dahoo de Zay ;
- `pexels-…` : licence Pexels.

Aucune de ces images n'entre en production sans licence confirmée (DESIGN.md). Toutes conviennent au dev local. On préfère une personne au travail : une image d'objets seuls ou de mains seules est marquée « à remplacer ».

| Emplacement                     | Candidat (chemin dans la banque)                                | `nom_origine`                                     | Licence cataloguée      | Statut                                                                                              |
| ------------------------------- | --------------------------------------------------------------- | ------------------------------------------------- | ----------------------- | --------------------------------------------------------------------------------------------------- |
| Hero (portrait, mobile d'abord) | `photos/metiers-services/equipe-nettoyage-appartement.jpg`      | `Jeflink-illustrations (79).jpg`                  | non renseignée          | À confirmer. Chez un client, salopettes orange en écho à l'accent.                                  |
| Hero (variante paysage)         | `photos/metiers-services/electricienne-cablage.jpg`             | `Jeflink-illustrations (96).jpg`                  | non renseignée          | À confirmer                                                                                         |
| Carte Électricité               | `photos/metiers-services/electricienne-cablage.jpg`             | `Jeflink-illustrations (96).jpg`                  | non renseignée          | À confirmer (si elle n'est pas le hero)                                                             |
| Carte Plomberie                 | `photos/metiers-services/compteurs-eau-plomberie.jpg`           | `Jeflink-illustrations (56).jpg`                  | non renseignée          | ⚠ objets seulement : à remplacer                                                                    |
| Carte Plomberie (variante)      | `photos/metiers-services/cles-molette-serre-tube.jpg`           | `Jeflink-illustrations (70).jpg`                  | non renseignée          | ⚠ objets seulement : à remplacer                                                                    |
| Carte Froid et clim             | `photos/metiers-services/climatiseur-mural-split.jpg`           | `Jeflink-illustrations (66).jpg`                  | non renseignée          | ⚠ appareil seul : à remplacer                                                                       |
| Carte Ménage                    | `photos/metiers-services/menage-nettoyage-table.jpg`            | `Jeflink-illustrations (60).jpg`                  | non renseignée          | À confirmer                                                                                         |
| Carte Ménage (variante)         | `photos/metiers-services/nettoyage-mur-eponge.jpg`              | `Jeflink-illustrations (80).jpg`                  | non renseignée          | À confirmer                                                                                         |
| Carte Petits travaux            | `photos/metiers-services/ouvrier-poncage-mur-chantier.jpg`      | `Jeflink-illustrations (95).jpg`                  | non renseignée          | À confirmer                                                                                         |
| Carte Électroménager            | aucun                                                           | —                                                 | —                       | **Manque** : seule `cuisine-equipee-bois.jpg` (cuisine vide) existe. Visuel générique en attendant. |
| Carte « Devenir pro »           | `photos/metiers-services/menuisier-tablier-etabli.jpg`          | `Jeflink-illustrations (85).jpg`                  | non renseignée          | À confirmer (artisan à son établi, sans légende nominative)                                         |
| À propos : Dakar                | `photos/culture-senegal/batiment-colonial-car-rapide-dakar.jpg` | `Sn-Dahoo-Immobilier (13).jpg`                    | non renseignée (Dahoo)  | À confirmer. Vraie scène de Dakar.                                                                  |
| À propos : rue (variante)       | `photos/culture-senegal/rue-taxis-jaunes-mosquee.jpg`           | `Sn-Dahoo-Immobilier (5).jpg`                     | non renseignée (Dahoo)  | À confirmer                                                                                         |
| Bandeau intérieur               | `photos/immobilier/sejour-bois-balcon-soleil.jpg`               | `Biens-dahoo-archives (5).jpg`                    | non renseignée (Dahoo)  | À confirmer (photo d'un bien réel : droits du propriétaire ?)                                       |
| Ville (variante tracée)         | `photos/commerce-marche/marche-rue-parasols-etalage.jpg`        | `pexels-el-bataky-photos-2156197228-36943010.jpg` | Pexels (d'après le nom) | Licence tracée ; lieu non vérifié (pas forcément le Sénégal)                                        |
| Images Open Graph               | aucune photo                                                    | —                                                 | —                       | Générées (texte et logo) : aucune licence en jeu                                                    |

- **Écartés.**
  - `portrait-technicienne-salopette-rouge.jpg` : visage face caméra, il se lirait comme « une pro Jeflink ».
  - `menuisier-perceuse-mains.jpg` : des mains seules.
  - Tout `photos/equipes-projets/`, `avatars/` et `logos/tiers/`.
  - `ile-goree-maisons-colorees.jpg` : Gorée est hors V1 (spec 002).
  - Les scènes religieuses (Touba, Magal), hors de propos pour un service marchand.
- **Emplacements sans candidat satisfaisant.** Plomberie, froid et clim (aucun humain au travail), électroménager (rien), et une scène « artisan chez un client à Dakar » pour le hero. Recommandation : un vrai shooting avec 3 ou 4 pros recrutés, avec une autorisation écrite de droit à l'image (Q9).
- **Visuels par métier, sans liste en dur.** Le web associe un visuel à un `icon_key` (`plumbing`, `electricity`, `cooling`, `appliance`, `cleaning`, `handyman`, spec 002), jamais à un slug. Un `icon_key` absent ou inconnu prend le visuel et le pictogramme génériques : un nouveau métier s'affiche sans déploiement.
- **Livraison.** Copie convertie dans `apps/web/public/images/site/…`, en WebP aux tailles affichées (hero 750 et 1 600 px, cartes 600 px, visuel de la page métier × quartier en 480 px pour le mobile), jamais l'original. Une ligne dans `docs/design/assets.md` pour chaque fichier (web 4).

## IA (si applicable)

Aucune. Pas de texte SEO généré par une IA : le contenu de masse est pénalisé, et les intros de quartier sont écrites par l'Ops. La recherche de quartier est la normalisation partagée (`matchSearch`), sans IA. La recherche en langage naturel (IA1) viendra dans `/demande`, côté serveur (règle 4).

## Revue terrain et arbitrages

Revue `terrain-reviewer` du 2026-10-05. Chaque affirmation de la copie publique a été vérifiée dans les specs 001 à 005 et dans le code.

**Intégré**

1. **Quartier dit avec ses mots** : champ « Votre quartier » en `GET` sans JS sur `/[metier]` et les 404, route `/recherche` (`matchSearch`), suggestions, issue WhatsApp. Alias des zones complétés par l'Ops, avec un critère d'acceptation.
2. **WhatsApp** :
   - amorces « Problème : … » et « Mon repère : … », variante « Je préfère en wolof » ;
   - CTA visible sans défilement, barre fixe en CSS sur l'accueil, `/[metier]` et `/[metier]/[quartier]` ;
   - test d'encodage et d'absence de donnée personnelle.
3. **Wolof** :
   - bandeau wolof sur l'accueil et `/devenir-pro`, seulement avec une formule validée par un locuteur (web 14, conditionnée à Q2) ; Q2 nomme le locuteur et une date ;
   - passe `design:ux-copy`, phrases de 12 mots au plus et formules interdites contrôlées automatiquement.
4. **Connexion** : la mention « Un code SMS vous sera envoyé » sur le CTA. Le lien « Je ne reçois pas le code » vers WhatsApp existe déjà (spec 001) et suffit pour la V1.
5. **Confiance** :
   - `SITE_INDEXABLE` conditionné (contrôle au démarrage, plus conditions de `chantier-prod.md`, dont la procédure « Pro vérifié ») ;
   - « Ce que Jeflink ne vous demande jamais » ;
   - FAQ anti-usurpation ;
   - numéro du support, horaires et nom de la société sur chaque page.
6. **Prix** :
   - phrase exacte de `catalog.priceNotice` écrite dans la spec, complétée par la règle de l'accord du client ;
   - FAQ « pour un proche » et « à l'étranger » fondées sur les specs 001 et 004 ;
   - aucun nom de moyen de paiement.
7. **Performance** :
   - profil 3G lente et seuil de 250 ko pour `/[metier]/[quartier]` ;
   - repli de police ajusté, `srcset` et `sizes` justes, sans lecture de `Save-Data` ;
   - menu replié sur les liens du pied de page sans JS ;
   - essai sur un vrai Android.
8. **Délai** :
   - FAQ « Quand le pro vient-il ? » sur les règles de la spec 003, valeurs dans `rules` ;
   - urgence citée (elle existe dans la spec 003) avec le lien `?urgence=1` ;
   - horaires du support sur chaque page de quartier.
9. **Secondaires intégrés** :
   - intros en français parlé, relues par un habitant ;
   - `/devenir-pro` avec message vocal, sans frais d'entrée ni abonnement (vrai : les abonnements sont exclus de la V1, la commission ne s'écrit qu'à la clôture, spec 005) ;
   - `og:description` en deux lignes, `tel:` exigé pour indexer ;
   - FAQ « à l'étranger » ;
   - images d'objets ou de mains seules marquées « à remplacer ».

**Faits vérifiés qui ont changé la copie**

- **Code de fin.** C'est le client qui le donne au pro, à la fin (spec 004). L'étape 03 devient « Travail fini ? Donnez votre code au pro ».
- **Moment du paiement.** Aucune spec ne fixe le moment du paiement ni n'interdit un acompte. Pas de « vous ne payez jamais à l'avance » ; à la place, « Ce que Jeflink ne vous demande jamais », et une nouvelle question (Q14).
- **Accord sur le prix.** `catalog.priceNotice` (« Prix de départ, le prix final est dans le devis. ») ne dit pas que le client valide le prix. Le site ajoute « Vous choisissez le devis. Le prix ne change jamais sans votre accord. » (règle de l'avenant, spec 004). Pas de « donné avant de commencer » : un avenant se propose pendant l'intervention.
- **Pour un proche.** C'est possible en V1 depuis un compte sénégalais (repère libre, « Partager à un proche », spec 004). Depuis l'étranger, la connexion est réservée aux numéros du Sénégal (spec 001, Q1) : la FAQ oriente vers un proche à Dakar ou WhatsApp.
- **Urgence.** Elle existe (case « C'est urgent », confirmation sous 1 h, spec 003) : d'où `?urgence=1`.
- **Connexion.** Le lien WhatsApp « Je ne reçois pas le code » existe déjà. Il est toujours visible, sans délai de 30 s, avec un message générique.
- **Usurpation.** Le SMS de connexion dit déjà « Ne le donnez à personne, ni à un artisan, ni à Jeflink » (spec 001). La FAQ s'appuie dessus.
- **Alias.** Le seed n'a pas « Yoff Virage » (seulement « Yoff Layène ») : c'est à compléter par l'Ops.

**Reporté** (hors du périmètre de cette spec, voir « Hors périmètre et suites »)

- Afficher le lien WhatsApp de la connexion après 30 s et y garder le métier et le quartier : c'est une modification de la spec 001.
- Compteur d'abandon entre la connexion et la demande : c'est un événement côté API (`analytics`).
- Rattachement d'un échange WhatsApp à une demande : spec 003 et agent WhatsApp (V2).
- Alias wolof des métiers et des quartiers : après Q2.

## Hors périmètre et suites

- Blog, portfolio ou « réalisations », témoignages, profils publics de pros (Passeport Pro, V3), espace pro public, inscription pro en ligne (app Pro, étape 6).
- Pages par service (`/plombier/debouchage`) et pages de quartier seules (`/quartiers/ouakam`) : le schéma d'URL reste métier × quartier.
- Version `wo` des pages publiques et sélecteur de langue : quand les textes seront validés (ADR 0013). Seul un bandeau wolof validé peut arriver en V1 (web 14).
- Formulaire de contact, demande sans compte (remplir avant de se connecter), recherche en langage naturel sur le site, carte interactive des zones, vidéo du hero.
- Mesure d'audience par un outil tiers (cookies, déclaration CDP). En V1, on compte les demandes `channel=web` côté API.
- Pages diaspora et entreprises (V3), désignation formelle d'un proche (V3), bannières et campagnes saisonnières (V2).
- Cache CDN du HTML, CSP par empreintes (SRI), purge du cache à la saisie Ops, domaine et TLS (`chantier-prod.md`).
- Pages `/conditions` et `/confidentialite` (déjà au chantier prod, « avant mise en ligne ») : le pied de page n'affiche leurs liens que lorsqu'elles existent.
- PWA et service worker.
- **Suites signalées par la revue terrain** :
  - spec 001 : lien WhatsApp de la connexion mis en avant après 30 s, avec un message qui reprend le métier et le quartier lus dans `next` ;
  - `analytics` : compteur d'abandon entre l'arrivée sur la connexion et la création de la demande ; signal « demande non servie » depuis la recherche de quartier du site (texte normalisé, sans identifiant) ;
  - spec 003 et WhatsApp (V2) : rattacher une conversation WhatsApp du support à une demande créée par l'Ops pour le client ;
  - alias wolof des métiers et des quartiers, saisis après validation par le locuteur de Q2.

## Critères d'acceptation

- [ ] En local, Awa va de l'accueil à `/plombier/ouakam`, puis à `/demande` pré-rempli (métier et quartier choisis, urgence si `?urgence=1`), en passant par la connexion si besoin. Le lien WhatsApp ouvre le message prérempli avec ses amorces.
- [ ] Sans JS : « Parcelles », « PA » et « Sacré-Cœur 3 » tapés dans « Votre quartier » mènent à la bonne page ; « Sacré » propose des quartiers ; « Gorée » propose WhatsApp et « Autre quartier ». Le texte tapé n'apparaît dans aucun journal applicatif.
- [ ] Les alias des 24 zones couvrent les noms dits, vérifiés par l'Ops sur une liste d'au moins 3 formes par grand quartier (dont « Parcelles », « PA », « Unité 15 », « Yoff Virage », « Sacré-Cœur 3 », « Sicap », « Patte d'Oie »).
- [ ] Un métier, un quartier ou une ouverture de métier saisi dans l'admin apparaît sur le site, et dans le sitemap s'il est indexable, sans déploiement et en 5 minutes au plus. Fermé, la page répond 404 et sort du sitemap.
- [ ] API arrêtée après un premier affichage : les pages déjà vues restent servies. API arrêtée sans aucune copie : l'accueil s'affiche, sans ses sections de données, avec le CTA WhatsApp. Aucune page ne répond 404 à cause d'une panne.
- [ ] Une paire sans intro de quartier porte `noindex, follow` et sort du sitemap. Avec une intro, elle est indexable et son titre utilise le locatif (« aux Almadies »).
- [ ] Aucun métier, quartier, prix ou chiffre en dur dans le code du web. Les règles chiffrées viennent de `rules`, les preuves de `stats`, et une section sous seuil n'est pas rendue (test avec des seuils non atteints).
- [ ] `/api/stats/` : seuils, arrondis, exclusions (pros de démo, comptes de revue) et règle « 3 pros distincts » testés ; aucun nom ni identifiant dans la réponse.
- [ ] `publicApi()` n'envoie jamais de cookie, d'`Authorization` ni d'en-tête du visiteur, et refuse tout chemin hors liste (tests). Aucune page de `app/(site)` n'importe `serverApi` (test d'architecture). Revue `security-reviewer` faite.
- [ ] Le test des slugs réservés passe : chaque segment de premier niveau de `apps/web/src/app` figure dans le JSON partagé, et Django refuse ces slugs.
- [ ] `robots.txt` interdit tout quand `SITE_INDEXABLE` n'est pas vrai. `SITE_INDEXABLE=true` refuse de démarrer sans `SITE_URL`, les deux numéros du support et `SITE_LEGAL_NAME`. Canonical, Open Graph et JSON-LD sont présents et valides sur les trois types de pages (validateur de données structurées).
- [ ] Chaque page affiche dans son pied de page le numéro du support, ses horaires et le nom de la société. Sur mobile, le CTA double est visible sans défilement, et la barre fixe ne masque jamais le focus.
- [ ] Message WhatsApp : test d'encodage (`é`, `ŋ`, sauts de ligne) et test d'absence de donnée personnelle.
- [ ] Budgets tenus et mesurés sur les deux profils (tableau « Performance »), valeurs dans la PR. Aucune dépendance ajoutée. Le payload d'une page publique ne contient aucune clé `requests.*` ni `bookings.*`.
- [ ] AA : navigation clavier, menu mobile (avec et sans JS), pause du bandeau, `prefers-reduced-motion`, cibles de 48 px, contraste. Revues `design-guardian` et `design:accessibility-review` faites.
- [ ] Toutes les chaînes dans `fr.json` (`site.*`). Phrases de 12 mots au plus, aucune formule interdite (tests), chaque réponse de FAQ rattachée à sa règle. Aucun texte wolof publié sans validation nominative (Q2). Chaque image livrée a sa ligne dans `assets.md`, avec son statut de licence.
- [ ] `make openapi` à jour, client TS régénéré.

## Tâches par couche

Chacune livrable et testable seule, dans l'ordre.

- api :
  1. **Slugs réservés partagés** :
     - `RESERVED_TRADE_SLUGS` passe dans un JSON versionné (`catalog/reserved_slugs.json`, avec les slugs de zones réservés), lu par `catalog` et `zones` ;
     - ajouts listés dans « Règles d'URL » ;
     - contrôle système : aucun `Trade` ni `Zone` existant ne porte un slug réservé ;
     - tests (refus dans l'admin, contrôle au démarrage).
  2. **Textes SEO saisis par l'Ops** :
     - `Trade.seo_intro_*`, `Zone.locative_*`, `Zone.seo_intro_*` (migrations additives), formulaires et filtre « intro vide » dans l'admin ;
     - validation : refus d'un numéro ou d'une URL ; `locative_fr` contient le nom de la zone ;
     - `seo_intro` dans le détail d'un métier ;
     - tests.
  3. **Détail d'une zone** : `GET /api/zones/{slug}/`, sélecteurs `nearby_zones(zone, trade=None, limit=4)` (PostGIS, distance entre les centres, jamais exposée) et `is_indexable(zone)`, filtre `?trade=`. Tests : zone inactive → 404, voisins limités au métier, ni position ni rayon dans la réponse, 304.
  4. **Couverture** : `GET /api/catalog/coverage/`, `COVERAGE_LIST_MAX`, `updated_at` = le plus récent du métier, de ses services et de la zone. Tests : paire fermée absente, métier ou ville inactifs, borne, 304.
  5. **Statistiques publiques** :
     - `analytics.selectors.public_stats` et `GET /api/stats/` ;
     - réglages `PUBLIC_STATS_*` ;
     - `rules` lu dans les réglages existants (devis, contestation, confirmation normale et urgente, heures de nuit) ;
     - lecture par les sélecteurs de `bookings`, `reviews` et `providers` ;
     - tests : chaque seuil, arrondis, exclusions `is_demo` et comptes de revue, règle des 3 pros distincts, `rules` égal aux réglages, filtres inconnus → 404, aucun identifiant dans la réponse.
  6. **Contrat et documentation** : `make openapi`, client régénéré. ARCHITECTURE.md (`analytics` expose des agrégats publics à seuils) et `apps/api/CLAUDE.md` (slugs réservés en JSON partagé, textes SEO sans numéro).
- données (Ops, dans l'admin, sans code) :
  1. **Alias** : compléter les alias des 24 zones avec les noms dits (« Yoff Virage », « Unité 15 », numéros de Sacré-Cœur et de Parcelles…) et ceux des métiers avec les mots courants en français (« fuite », « coupure », « frigoriste »…). Liste vérifiée par le critère d'acceptation.
  2. **Textes** : 24 intros de quartier et leurs locatifs, 6 intros de métier, en français parlé, relus par un habitant (Q3).
- web :
  1. **Socle du site public** :
     - groupes de routes `(site)` et `(espace)` (`/connexion`, `/demande`, `/compte` gardent leurs URL), avec `Providers` dans `(espace)` seulement ;
     - layout public : en-tête, menu mobile (lien vers le pied de page sans JS, `<dialog>` avec JS), pied de page (liens, numéro du support, horaires, `SITE_LEGAL_NAME`), lien d'évitement ;
     - `SITE_URL`, `SITE_INDEXABLE`, `SITE_LEGAL_NAME` et `SUPPORT_PHONE_NUMBER` dans `lib/site-config.ts` et `.env.example` (noms seulement), avec le contrôle « `SITE_INDEXABLE=true` exige… » ; `metadataBase` ;
     - redirection 308 des majuscules dans `src/proxy.ts`, helper de chemin unique (ADR 0013) ;
     - messages transmis au client limités aux îlots ;
     - tests : proxy, configuration (dont le refus de démarrer), payload sans clés `requests.*`.
  2. [sécu] **`publicApi()`** :
     - dans `@jeflink/api-client/bff` (ou `lib/public-api.ts`) : `GET`, préfixes autorisés, liste fermée d'en-têtes, cache de données 300 s avec étiquettes, dernière copie en cas d'échec ;
     - test d'architecture (aucun `serverApi` sous `(site)`) ;
     - tests : aucun cookie, aucun jeton, aucun en-tête du visiteur, chemin refusé, `POST` refusé ;
     - revue `security-reviewer`.
  3. **Composants du site** :
     - pictogrammes par `icon_key` avec un générique (SVG en ligne), `TradeLabel` (pictogramme et libellé) ;
     - `PriceFrom` (avec `catalog.priceNotice` et la phrase sur l'accord du client) ;
     - `CtaPair` (demande et WhatsApp, amorces, variante wolof, mention du code SMS) et `ActionBar` (barre fixe en CSS) ;
     - `ZoneSearchForm` (`GET`, libellé et exemple) ;
     - `SectionNumber`, `Marquee` (CSS, pause, mouvement réduit), `Faq` (`<details>`), `StatFigure` (rendu nul sous seuil) ;
     - tests unitaires des fonctions pures : message WhatsApp (encodage, aucune donnée personnelle), lien pré-rempli, repli du locatif, choix des chiffres.
  4. **Images** : conversion des candidates retenues (WebP aux tailles affichées) dans `public/images/site/`, registre des visuels par `icon_key` avec un générique, `alt` en i18n, une ligne par fichier dans `docs/design/assets.md` avec son statut de licence. Mesure du poids.
  5. **Accueil** : les sections dans l'ordre décidé plus haut, barre d'actions mobile, dégradation sans données, aucune chaîne en dur. Mesure Lighthouse sur les deux profils.
  6. **`/metiers` et `/[metier]`** : liste des métiers, page métier (intro, services, prix et mentions, quartiers ouverts en liens, champ « Votre quartier », comment ça marche, « Quand le pro vient-il ? », FAQ courte, CTA), redirection 307 des alias, `notFound` seulement sur un vrai 404.
  7. **`/[metier]/[quartier]`** :
     - titre avec le locatif, intro du quartier, voisins, autres métiers, chiffres à seuil ;
     - lien « C'est urgent ? », horaires du support, barre d'actions ;
     - `noindex` si la paire n'est pas `indexable`, 404 utile, erreur distinguée de l'absence ;
     - tests de la règle d'indexation et des 404 ;
     - budget de 250 ko vérifié.
  8. **`/recherche`** : égalité → 307, préfixes → suggestions, zone fermée pour ce métier → autres métiers, rien → WhatsApp et « Autre quartier » ; `noindex`, texte limité à 40 caractères, jamais journalisé ni recopié. Tests sur les exemples du critère d'acceptation.
  9. **`/demande` pré-rempli** :
     - lecture de `metier`, `quartier`, `service` et `urgence` (slugs validés contre le catalogue, sinon ignorés) ;
     - priorité de l'URL sur le brouillon pour le métier, le quartier et l'urgence ; le service est vidé si le métier change ;
     - retour après connexion avec la requête intacte ;
     - tests.
  10. **SEO** : helpers de métadonnées (titre, description, `og:description` courte, canonical), JSON-LD (`Organization`, `WebSite`, `Service`, `BreadcrumbList`), `sitemap.ts` (via `coverage`), `robots.ts` (`SITE_INDEXABLE`, `/recherche` exclu), images Open Graph (`next/og`, polices OFL versionnées, 100 ko au plus). Tests : sitemap sans paire non indexable, robots selon la configuration, JSON-LD sans prix quand aucun n'est saisi.
  11. **Pages sœurs** : `/a-propos`, `/contact` (WhatsApp, appel, horaires), `/devenir-pro` (si Q10 est acceptée : message vocal, pas de frais d'entrée, commission à la mission terminée, taux visible avant chaque devis).
  12. **404 et erreurs publiques** : `not-found` global et `not-found` du métier, `error.tsx` public, avec champ « Votre quartier », liens depuis le cache si disponibles, WhatsApp, accueil.
  13. **Copie et revues** :
      - textes `site.*` validés par Zay, passes `design:ux-copy` et `humanizer` ;
      - tests sur `fr.json` : phrases de 12 mots au plus, formules interdites, présence d'une référence de règle pour chaque réponse de FAQ ;
      - revues `design-guardian` et `design:accessibility-review`, revue `terrain-reviewer` de la copie ;
      - mesures des deux profils dans la PR, essai sur un vrai Android d'entrée de gamme.
  14. **Bandeau wolof** (seulement si Q2 a nommé un locuteur et qu'il a validé la formule) : une phrase courte, `site.woBanner`, `lang="wo"`, sur l'accueil et `/devenir-pro`, avec le bouton « Je préfère en wolof ». Le texte et le nom du valideur sont notés dans la PR. Sans validation, rien n'est affiché : pas de wolof écrit par nous.
- docs :
  1. ADR 0013 accepté après validation. `apps/web/CLAUDE.md` : JSON-LD `Service`, `Organization` et `BreadcrumbList` (sans `LocalBusiness`), `publicApi()`, groupes de routes, aucune lecture de session dans `(site)`. `DESIGN.md` › Web public : jamais de texte sur une photo, bandeau avec pause, barre d'actions mobile, rayon unique. `assets.md` (web 4). Registre des traitements : support par WhatsApp et par téléphone. Ajouts à `chantier-prod.md` :
     - conditions de passage à `SITE_INDEXABLE=true` : procédure « Pro vérifié » écrite dans `docs/ops/` (Q7), numéro de service WhatsApp et appel avec horaires tenus (Q8), raison sociale (Q15), licences des images ou shooting (Q9), intros relues (Q3) ;
     - `SITE_URL` en production ;
     - cache CDN du HTML et CSP par empreintes (SRI), après mesure ;
     - purge du cache de Next à la saisie Ops ;
     - Search Console et soumission du sitemap ;
     - suites de la revue terrain (spec 001, `analytics`, rattachement WhatsApp).
- console : rien (saisie des textes dans l'admin Django).
- client / pro : rien.

### Écarts d'implémentation connus (2026-10-05)

- **`publicApi()` sans secret du BFF.** En-têtes `Accept` et `Accept-Language: fr` seulement, ni cookie, ni jeton, ni en-tête du visiteur. L'API voit donc l'IP du serveur Next, et la limite `catalog_read` est partagée par tout le site : portée dédiée au chantier prod (C2).
- **`ActionBar` en `sticky`** plutôt qu'en `fixed` : la barre reste dans le flux, sans marge à réserver, et ne masque pas le focus.
- **Cache `fetch`** (`revalidate: 300`, étiquettes, copie de secours) plutôt que `"use cache"`, qui suppose Cache Components, incompatible avec la CSP à nonce (ADR 0013).
- **Règles de `/api/stats/` durcies** :
  - les missions et la note ne sortent qu'au-dessus de la règle des pros distincts, filtrées ou non ;
  - la note n'est jamais donnée par zone ;
  - le `count` de la note est arrondi ;
  - `?zone=` seul est refusé (il faut aussi `?trade=`).
- Suites des revues `security-reviewer` (C2, N1, N3, N4, N5, N7) et `terrain-reviewer` : consignées dans `chantier-prod.md`.

## Questions à trancher (Zay)

1. **Q1 — Rendu des pages publiques (ADR 0013).** Proposition : rendu à chaque requête avec la CSP à nonce actuelle, et les données de l'API en cache 5 minutes (dernière copie servie si l'API tombe). Pas d'ISR en V1 ; cache CDN et CSP par empreintes au chantier prod, mesures en main.
   _Recommandation : accepter._ On garde la sécurité de la spec 001 sans perdre la tenue à la panne.
2. **Q2 — Wolof.** Proposition :
   - français sans préfixe ; wolof sous `/wo/…` avec les mêmes slugs, publié seulement quand les textes sont validés ;
   - en V1, pages en français et, si possible, un bandeau wolof validé sur l'accueil et `/devenir-pro`.
     _Recommandation : accepter, et nommer maintenant le locuteur qui écrit ou valide le wolof, avec une date. Sans nom, pas de bandeau._
3. **Q3 — Indexation des pages métier × quartier.** Proposition : indexable si le quartier a un texte d'intro saisi ; sinon `noindex, follow` et hors sitemap. Concrètement, 24 textes de 2 à 4 phrases, plus les 6 intros de métier.
   _Recommandation : accepter. Textes en français parlé avec des repères connus, relus par un habitant de chaque quartier, avant `SITE_INDEXABLE=true` ; l'agent peut proposer des brouillons._
4. **Q4 — Formulaire de contact.** Proposition : aucun en V1. WhatsApp, appel et horaires suffisent.
   _Recommandation : accepter._ Pas de donnée personnelle collectée, pas d'anti-spam, pas d'endpoint.
5. **Q5 — Preuves sociales.** Proposition : `/api/stats/` avec des seuils (50 missions, 20 avis, 5 pros ; 3 pros pour un filtre), arrondis à la dizaine, sections masquées sous les seuils. Au lancement, des chiffres vrais par construction : « 3 devis au plus », « 48 h pour signaler un problème », « 0 F de frais Jeflink pour vous ».
   _Recommandation : accepter, et confirmer que la V1 ne facture rien au client._
6. **Q6 — « Travail garanti » en V1.** Ni remboursement, ni reprise gratuite, ni séquestre avant la V2. Proposition : garder la signature et l'expliquer par ce qui existe : pro vérifié, prix choisi et jamais changé sans votre accord, code de fin et photos, 48 h pour signaler un problème, Jeflink examine.
   _Recommandation : accepter, sans « remboursé » ni « reprise gratuite » avant la V2._
7. **Q7 — « Pro vérifié ».** La procédure n'est pas écrite (`docs/ops/`).
   _Recommandation : fixer la liste réelle (par exemple identité vue en personne, téléphone vérifié, référence terrain), l'écrire dans `docs/ops/`, n'afficher qu'elle. Pas d'indexation avant._
8. **Q8 — Support publié.** Le numéro WhatsApp du support est aujourd'hui le tien.
   _Recommandation : avant `SITE_INDEXABLE=true`, un numéro de service (WhatsApp Business et appel), des horaires tenus (par exemple 8 h – 20 h, tous les jours, à confirmer) et quelqu'un qui répond en wolof. Le bouton « Je préfère en wolof » en dépend._
9. **Q9 — Images.** Pas de licence tracée pour les photos de métiers ni pour les photos Dahoo. Aucune scène humaine pour la plomberie, le froid et clim, et l'électroménager.
   _Recommandation : candidates en local ; avant la mise en ligne, retrouver les licences ou, mieux, un shooting avec 3 ou 4 pros recrutés (autorisation écrite de droit à l'image)._
10. **Q10 — `/devenir-pro`.** Proposition : une page légère, avec le message vocal sur WhatsApp, sans inscription en ligne. Elle dit « pas de frais d'entrée, commission sur chaque mission terminée ».
    _Recommandation : accepter._ Le recrutement des 50 premiers pros a besoin d'une adresse à donner.
11. **Q11 — Données structurées.** Proposition : `Organization`, `WebSite`, `Service` et `BreadcrumbList`, sans `LocalBusiness` par quartier ni `AggregateRating`.
    _Recommandation : accepter, et corriger `apps/web/CLAUDE.md`. Un `LocalBusiness` unique le jour où un bureau physique existe._
12. **Q12 — Connexion avant la demande.** `/demande` exige le code SMS avant le formulaire (spec 003).
    _Recommandation : garder en V1. Le site prévient (« Un code SMS vous sera envoyé »), WhatsApp reste au même rang, et le lien « Je ne reçois pas le code » existe déjà. Le compteur d'abandon et « remplir d'abord » sont des suites._
13. **Q13 — Mesure d'audience.** Proposition : aucun outil tiers en V1 ; demandes `channel=web` et Search Console.
    _Recommandation : accepter._ Un outil auto-hébergé sans cookie pourra venir plus tard, par un ADR.
14. **Q14 — Moment du paiement au pro.** Aucune spec ne dit si le client paie à la fin, ni si un acompte (pour des pièces, par exemple) est permis.
    _Recommandation : fixer la règle « paiement à la fin, acompte seulement s'il figure dans le devis accepté » avec la spec suivante sur les devis. D'ici là, le site n'en parle pas._
15. **Q15 — Nom de la société publié.** Le pied de page affiche le nom de la société (`SITE_LEGAL_NAME`) contre l'usurpation, et la loi l'attendra.
    _Recommandation : donner la raison sociale (ou le nom provisoire, tant que la société n'est pas immatriculée) avant `SITE_INDEXABLE=true`._
