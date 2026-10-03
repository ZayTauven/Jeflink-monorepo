# ADR 0011 — Stockage d'objets et photos : envoi par l'API, réencodage avant stockage, URL signées

Statut : proposé · 2026-10-03 · Spec : `docs/specs/004-mission-completion-reviews.md`

## Contexte

La spec 004 apporte les premiers fichiers : les photos avant et après d'une intervention, prises dans le logement du client. Le stockage S3 compatible (SeaweedFS, service `s3` de `infra/docker-compose.yml`) tourne en local, mais Django ne s'en sert pas encore. Trois contraintes :

- **Données personnelles.** Une photo de téléphone porte souvent un EXIF avec la position GPS du domicile. Elle ne doit jamais être stockée telle quelle.
- **Terrain.** Le réseau est faible et les téléphones modestes. L'envoi doit pouvoir être rejoué, et la lecture rester légère.
- **Suite.** Le KYC (pièces, selfies), les photos et les notes vocales des demandes, puis le chat, utiliseront le même stockage.

## Décision

- **Bibliothèque** : `django-storages[s3]` (boto3), plus Pillow pour les images. Un stockage nommé `photos` dans `STORAGES`, sur un bucket privé. En test, `InMemoryStorage` remplace S3 : aucun réseau. Réglages : `S3_ENDPOINT`, `S3_PUBLIC_ENDPOINT`, `S3_BUCKET` et deux identifiants d'accès (valeurs factices en local, secrets ailleurs). La commande `ensure_bucket` crée le bucket, en local seulement.
- **Envoi par l'API**, en multipart, avec `Idempotency-Key`, plutôt qu'un envoi direct au stockage par URL présignée. Dans la requête, l'API :
  1. vérifie l'image en la décodant, avec la taille décodée bornée ;
  2. la redresse ;
  3. la réduit à 1 600 px ;
  4. la réencode en WebP sans aucune métadonnée.

  Seul ce résultat est écrit : l'original et son GPS ne touchent jamais le stockage.

- **Miniature en tâche Celery** (`make_thumbnail`, 400 px, WebP, idempotente). L'image pleine reste disponible pendant ce temps.
- **Lecture par URL signées courtes** (10 min), produites par un client boto3 configuré sur `S3_PUBLIC_ENDPOINT`. La signature dépend de l'hôte, et le navigateur ne voit pas `http://s3:8333`. Aucune URL publique permanente, et les fichiers ne passent pas par l'API ni par le BFF.
- **Clés d'objet** formées de `public_id` seulement (`bookings/<réservation>/<photo>.webp`). Une clé ne contient jamais de nom, de numéro ni de date de naissance.

## Conséquences

- Le GPS ne peut pas fuir par le stockage, et le contrôle de type se fait côté serveur. Une seule requête suffit : pas de confirmation après un envoi direct.
- L'app Pro (étape 6) compressera avant l'envoi (environ 500 Ko). L'envoi par l'API reste donc court.
- − Un worker Django est occupé pendant l'envoi et le réencodage (quelques centaines de ms). En production, il faudra une limite de taille du corps et des délais au proxy (`chantier-prod.md`).
- − Le web affiche des URL signées : `next/image` en `unoptimized`, avec l'hôte du stockage dans `remotePatterns`. Une URL expirée se renouvelle à l'actualisation de la page.
- Le KYC et les pièces jointes de la demande réutiliseront `common.storage`, avec leurs propres règles d'accès.

## Alternatives écartées

- **URL présignée pour un envoi direct au stockage**, puis traitement en quarantaine. L'API reste libre pendant l'envoi, mais l'original et son GPS sont stockés, même brièvement. Il faut aussi exposer le stockage en CORS et ajouter une étape de confirmation. À reconsidérer si le volume l'exige.
- **Lecture des fichiers à travers l'API et le BFF** : chaque image coûterait un aller-retour par Django et Next.
- **Stockage sur disque (`FileSystemStorage`)** : il ne correspond pas à la production et serait à migrer.
