# Chantier prod

Depuis le 2026-10-03, on livre d'abord les fonctionnalités en dev local. Le durcissement de production est regroupé ici et traité en dernier, avant la mise en ligne.

Règle : un besoin prod repéré pendant une feature s'ajoute à cette liste, avec sa source. On ne le traite pas pendant la feature. Les règles non négociables de `CLAUDE.md` (argent, machine à états, IA côté serveur, i18n, données perso dans les logs, contrat OpenAPI) ne sont pas du durcissement prod : elles s'appliquent dès le dev.

## Ordre des features

1. Clôture de la spec 001 (comptes) : fusion dans `main`.
2. Catalogue et zones (métiers et quartiers en données ; Ops par l'admin Django au début).
3. Demande → devis → réservation (machine à états).
4. Code de fin, photos, avis.
5. Portefeuille Pro et commission sur le cash.
6. Apps client et Pro, puis pages SEO métier × quartier.

## Reporté depuis la spec 001

| Élément                                                      | Source                     | Quand                         |
| ------------------------------------------------------------ | -------------------------- | ----------------------------- |
| Adaptateur SMS réel, DLR                                     | spec 001, api 20 (Q7)      | chantier prod                 |
| Alertes `onSecurityEvent` branchées sur la supervision       | spec 001, revue web 1, m-9 | chantier prod                 |
| Console : BFF, CSP, politique de session Ops                 | spec 001, web/console 3    | quand on construit la console |
| Console : `/connexion` + TOTP, gardes de route               | spec 001, web/console 4    | quand on construit la console |
| Client et Pro : session, OTP, Mon compte, file hors ligne    | spec 001, client/pro 1 à 6 | étape 6 (apps mobiles)        |
| Numéro WhatsApp du support dédié (provisoire : celui de Zay) | spec 001, web 2            | quand la boîte le fournit     |
| Pages `/conditions` et `/confidentialite`                    | spec 001, web 2            | avant mise en ligne           |
| Audio d'aide « Je ne reçois pas le code », textes `wo`       | spec 001, web 2 (Q12)      | avant mise en ligne           |

## Besoins prod relevés pendant les features

| Besoin                                                                                                                                                                                                                                      | Source                         |
| ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------ |
| Cache CDN des endpoints publics `/api/catalog/*` et `/api/zones/*` (réponses anonymes seulement, jamais avec `Authorization`), purge après une saisie dans l'admin                                                                          | spec 002, api 4                |
| Admin Django modifiable (`catalog`, `zones`) : vérifier qu'il reste sur l'hôte interne, et prévoir l'accès de l'Ops qui saisit (VPN ou équivalent)                                                                                          | spec 002, Q6                   |
| Pages publiques du web servies depuis le cache (ISR) : régler la revalidation et le comportement si l'API ne répond pas                                                                                                                     | spec 002, web 1                |
| Retirer `Accept-Language` du `Vary` des endpoints publics du catalogue (ajouté par `LocaleMiddleware`, alors que la réponse ne dépend pas de la langue, ADR 0009), pour ne pas fragmenter le cache CDN                                      | spec 002, api 4                |
| Supervision de Celery beat : l'expiration des demandes et des devis, et l'annulation des réservations non confirmées, en dépendent (alerte si beat s'arrête ou prend du retard)                                                             | spec 003, api 3 à 5            |
| Admin Django (`providers`, `requests`, `analytics`) : mêmes précautions que le catalogue (hôte interne, accès des groupes `Validation pros` et `Saisie catalogue`) ; l'Ops y voit des demandes sans repère ni description                   | spec 003, api 1 à 3            |
| Pros réels : création par `manage.py onboard_provider` (opérateur Admin) en attendant l'inscription « Devenir pro » de l'app Pro ; procédure de vérification à écrire dans `docs/ops/` avant le premier recrutement                         | spec 003, api 1                |
| Notifications : `NOTIFICATIONS_ADAPTER` vaut `none` hors local/test ; brancher push puis SMS (idempotence, repli, désabonnement) et alerter si un envoi échoue                                                                              | spec 003, api 6                |
| Rétention des demandes et réservations : le repère et la position d'une demande close avec réservation restent jusqu'à la durée fixée à l'étape 4 (garantie, litiges) ; déclarer le traitement à la CDP                                     | spec 003, api 3                |
| Limite de 10 créations de demande par jour : fermée si Redis tombe (503) ; vérifier le dimensionnement du Redis d'auth et l'alerte `ratelimit_unavailable`                                                                                  | spec 003, api 3                |
| Redémarrer `worker` et `beat` à chaque déploiement qui change les tâches planifiées (`requests.tasks.expire_due`, `purge_locations`, `bookings.tasks.cancel_unconfirmed`)                                                                   | spec 003, api 3 à 5            |
| Limite par compte des signaux `UnservedDemand` (anti-pollution), et aucun signal pour un compte `is_review_account`                                                                                                                         | spec 003, revue sécurité       |
| Limite des renvois de devis par (pro, demande) et des envois par pro sur 24 h, avant de brancher push et SMS                                                                                                                                | spec 003, revue sécurité       |
| Test d'architecture élargi : `.update(`, `.create(`, `setattr` et `**` sur `status` partout dans `jeflink/`                                                                                                                                 | spec 003, revue sécurité       |
| Refuser une position hors de la zone choisie (`422 location_invalid`, avec marge)                                                                                                                                                           | spec 003, revue sécurité       |
| Lancer `manage.py check --database default` à chaque déploiement, pour `providers.E001` (pros de démo hors local/test)                                                                                                                      | spec 003, revue sécurité       |
| Stockage d'objets en production : bucket privé, identifiants dédiés, `S3_PUBLIC_ENDPOINT` en HTTPS, chiffrement au repos, sauvegarde ; limite de taille du corps (10 Mo) et délais d'envoi au proxy                                         | spec 004 (brouillon), ADR 0011 |
| Supervision des tâches `close_due`, `no_show_check`, `make_thumbnail` et de la purge des photos ; redémarrer `worker` et `beat` quand elles changent                                                                                        | spec 004 (brouillon)           |
| Rotation de `DATA_ENCRYPTION_KEYS` (code de fin chiffré) ; adaptateur SMS réel de `notifications` pour les SMS métier (`completion_code.sms`, `amendment.proposed`, `booking.dispute_reminder`), gabarits rendus côté serveur               | spec 004 (brouillon)           |
| Supervision des tâches `close_due`, `remind_disputes`, `confirm_no_shows`, `no_show_check`, `make_thumbnail`, `purge_photos`, `purge_contact` (alerte si beat s'arrête) ; redémarrer `worker` et `beat` à chaque déploiement qui les change | spec 004, api 2 à 5            |
| Groupes d'admin `Médiation` et `Modération avis` : comptes techniques nommés, second facteur, hôte interne ; procédure Ops « joindre le client avant de trancher » à écrire dans `docs/ops/`                                                | spec 004, api 3, 7, 8          |
| Photos du logement : déclarer le traitement à la CDP (rétention 12 mois, URL signées de 10 min, consultation Ops auditée) ; sauvegarde du bucket et suppression des objets à la purge                                                       | spec 004, api 5 et 7           |
| Taille des envois : limite de corps à 10 Mo et délais d'envoi au proxy ; un worker Django est occupé pendant le réencodage (quelques centaines de ms)                                                                                       | ADR 0011, spec 004             |
| Adaptateur SMS réel pour `completion_code.sms`, `amendment.proposed`, `booking.dispute_reminder` (gabarit GSM-7 rendu côté serveur, plafonds de SMS métier) ; le code de fin ne doit jamais apparaître dans les journaux du fournisseur     | spec 004, api 4 et 9           |
| Rotation de `DATA_ENCRYPTION_KEYS` : ajouter une clé en tête, chiffrer à nouveau les codes encore actifs, puis retirer l'ancienne                                                                                                           | spec 004, api 4                |
| Pros de démonstration exclus des moyennes d'avis : prévoir un jeu de données de recette avec de vrais avis pour la préproduction                                                                                                            | spec 004, api 8                |
| Fin `no_code` traitée à part pour la commission : le gestionnaire de clôture de `wallet` lit `completion_method` avant d'écrire `pro_commission_due` ; la notification `booking.completed_no_code` part en SMS                              | spec 004, revue sécurité       |
| Réencoder les photos hors de la transaction et des verrous de la réservation, et baisser `IMAGE_MAX_PIXELS` (40 M aujourd'hui)                                                                                                              | spec 004, revue sécurité       |
| Tâche de rapprochement des objets photo orphelins (objet écrit mais ligne absente, ou ligne purgée sans suppression)                                                                                                                        | spec 004, revue sécurité       |
| `purge_contact` limité aux demandes qui ont encore un repère ou une position (éviter de réécrire les lignes déjà vidées)                                                                                                                    | spec 004, revue sécurité       |
| Durée de conservation du texte des litiges : 12 mois après la clôture, puis effacement                                                                                                                                                      | spec 004, revue sécurité       |
| Détection des avis de complaisance : numéro ou appareil du client qui recoupe celui du pro                                                                                                                                                  | spec 004, revue sécurité       |
| Vérifier au démarrage que le bucket refuse la lecture anonyme (hors local)                                                                                                                                                                  | spec 004, revue sécurité       |
| Supervision de `flag_stuck` et de l'alerte `booking_stuck` ; l'Ops traite les missions bloquées par l'action « Annuler la mission »                                                                                                         | spec 004, revue sécurité       |
| `STORAGE_PUBLIC_ORIGIN` du web (origine publique du stockage des photos, autorisée dans la CSP `img-src`) : obligatoire en production, en https ; vide, aucune photo ne s'affiche                                                           | spec 004, web 2                |
| Garde-fou de mise en service de la commission : en production, taux par défaut à 0 jusqu'à la livraison de l'écran portefeuille de l'app Pro (étape 6) ; le vrai taux est saisi ensuite avec une date d'effet                               | spec 005, revue terrain (B6)   |
| Comptes marchands Wave et Orange Money au nom de Jeflink (entité enregistrée), frais de canal chiffrés sur les petits montants, accès au relevé pour le groupe `Rapprochement`                                                              | spec 005, revue terrain (Q7)   |
| Fiscalité de la commission : TVA (18 %) et facture de commission validées avec un comptable ; durée de conservation des écritures (10 ans proposés) déclarée à la CDP                                                                       | spec 005 (Q11, Q12)            |
| Supervision des tâches `remind_debts`, `watch_settlements` et `purge_payer_last4` (alerte si beat s'arrête) ; l'alerte `wallet_settlements_overdue` et `wallet_rate_missing` vont à l'Ops                                                   | spec 005, api 3, 5, 7, 9       |
| Groupes `Rapprochement` et `Comptabilité` : comptes techniques nommés, second facteur, hôte interne ; procédure Ops du rapprochement (relevé marchand, renvoi « à corriger », espèces avec reçu) à écrire dans `docs/ops/`                  | spec 005, api 5 et 6           |
| Adaptateur SMS réel pour `wallet.quotes_blocked` et `wallet.settlement_needs_correction` (gabarits GSM-7 rendus côté serveur, sans référence de transaction)                                                                                | spec 005, api 3 et 5           |
| Seuils de dette en réglages (`WALLET_DEBT_*`) : une pause pendant les fêtes demande un déploiement ; à reconsidérer (seuils en données) après les premiers mois                                                                             | spec 005, revue terrain (B4)   |
