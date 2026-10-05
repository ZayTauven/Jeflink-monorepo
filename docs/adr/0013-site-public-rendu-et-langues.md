# ADR 0013 — Site public : rendu à la requête avec données en cache, une URL par langue

Statut : accepté · 2026-10-05 · Spec : `docs/specs/006-site-public.md`

## Contexte

Le site public (`apps/web`) devient le premier canal d'acquisition : pages métier et métier × quartier (`/plombier/ouakam`) générées depuis `catalog` × `zones`. Quatre contraintes existent déjà :

- **CSP à nonce.** `src/proxy.ts` (spec 001) pose une CSP à nonce neuve à chaque requête. La documentation embarquée de Next 16 (`content-security-policy.md`) est nette : avec un nonce, toutes les pages sont rendues à la requête, l'ISR et le prérendu partiel sont exclus.
- **Langue par cookie.** `src/i18n/request.ts` lit `NEXT_LOCALE` : une même URL change de langue selon le visiteur. Un robot ne voit que le français, et aucun `hreflang` n'est possible.
- **Espace de noms partagé.** `/[metier]` est à la racine : un slug de métier peut masquer une page (`/contact`) ou un fichier de Next (`/opengraph-image`). `RESERVED_TRADE_SLUGS` (spec 002) protège une partie des cas, en Python seulement.
- **Pas de wolof écrit.** `wo.json` est vide et les libellés `wo` du catalogue aussi (ADR 0009). Publier des pages `wo` aujourd'hui, ce serait publier des doublons du français.

## Décision

- **Rendu à la requête, CSP à nonce conservée** sur toutes les pages, publiques comprises. Pas de `generateStaticParams` ni d'ISR en V1.
  - Les données publiques (catalogue, zones, statistiques) passent par un accès public du BFF, `publicApi()` : `GET` seulement, liste fermée de chemins, sans cookie, sans jeton et sans en-tête propre au visiteur.
  - Elles sont gardées dans le cache de données de Next (revalidation 5 min, étiquettes `catalog`, `zones`, `stats`). Si l'API ne répond pas, la dernière copie est servie.
  - Une page publique ne lit jamais la session. Son HTML est le même pour tous les visiteurs, ce qui permettra un cache CDN plus tard.
- **Slugs réservés : une seule liste**, dans un fichier JSON versionné côté API. Django la lit, et un test du web vérifie que chaque segment de premier niveau de `apps/web/src/app` y figure. On y ajoute `fr`, `wo`, `en` et les noms de fichiers de métadonnées de Next. Le second niveau (`/[metier]/[quartier]`) réserve `opengraph-image` et `twitter-image` pour les zones.
- **Langues : une URL par langue.**
  - Le français est servi sans préfixe (`/plombier/ouakam`). Le wolof le sera sous `/wo/…`, avec les mêmes slugs (préfixe « au besoin »).
  - Les pages `wo` ne seront publiées, avec `hreflang` (`fr`, `wo`, `x-default` vers `fr`), que lorsque leurs textes auront été validés par un locuteur.
  - D'ici là, les pages publiques sont en français seulement, sans sélecteur de langue. Le cookie garde son rôle pour les pages de l'espace client (non indexées).
- **Indexation pilotée par la configuration** : `SITE_URL` (URL canonique) et `SITE_INDEXABLE` (faux par défaut). Faux donne un `robots.txt` qui interdit tout et un `noindex` global, en local comme en staging. Vrai exige, au démarrage, `SITE_URL`, les deux numéros du support (WhatsApp et appel) et `SITE_LEGAL_NAME` ; les conditions non vérifiables en code (procédure « Pro vérifié », licences des images) sont listées dans `chantier-prod.md`.

## Conséquences

- La CSP reste stricte partout. Une faille XSS sur une page publique ne peut pas appeler le BFF avec les cookies du visiteur.
- Le site tient debout quand l'API tombe, tant qu'une copie est en cache. Une fermeture de quartier par l'Ops met 5 minutes au plus à se voir.
- − Chaque vue est rendue par le serveur : le coût CPU est plus élevé, le TTFB un peu plus long, et le HTML n'est pas en cache CDN. C'est acceptable au lancement. On mesurera avant de passer, au chantier prod, à une CSP par empreintes (SRI, expérimental dans Next 16) avec un cache CDN.
- − L'arrivée du wolof déplacera les pages sous un segment `[locale]`. Ce refactor est accepté et borné : les liens passent dès maintenant par un helper de chemin unique, et les slugs ne sont pas traduits.
- Un nouveau métier ne peut plus masquer une page ou un fichier de Next. La liste est vérifiée des deux côtés.

## Alternatives écartées

- **Pages publiques statiques ou ISR, avec une CSP sans nonce (`'unsafe-inline'`)** : rapide et cacheable, mais la protection contre les XSS est affaiblie sur la même origine que le BFF et ses cookies de session.
- **SRI expérimental dès maintenant** : la fonction est marquée expérimentale, et sa compatibilité avec les scripts en ligne de Next reste à vérifier. À reconsidérer au chantier prod, mesures en main.
- **Langue par cookie sur les pages publiques** : la page n'est pas indexable en `wo`, aucun `hreflang` n'est possible, et le cache se fragmente par visiteur.
- **Sous-domaine `wo.jeflink…`** : DNS et certificats en plus, et l'autorité SEO est divisée entre deux hôtes.
- **Préfixe pour toutes les langues (`/fr/…`)** : URL plus longues à partager sur WhatsApp, et une redirection de plus depuis la racine.
