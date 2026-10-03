# Spec 004 — Déroulé de la mission, code de fin, photos, avis

Statut : validée · 2026-10-03 (Zay) · ADR lié : 0011 (stockage d'objets et photos, accepté) · Revue `terrain-reviewer` intégrée (Q1 à Q7 acceptées avec ajustements)

## Problème

Awa a choisi Ibou, et la réservation est `scheduled` (spec 003). Rien ne trace encore la suite : l'arrivée, le prix qui change sur place, la fin du travail, sa qualité. C'est là que la confiance se perd (PRODUCT.md §2) et que se jouent les signatures : code de fin, photos avant et après, avenant validé par le client, avis vérifiés. Cette spec active `scheduled` → `closed`, sans argent. La commission (étape 5) s'accrochera à la clôture.

| Zone sensible        | Touchée ?      | Détail                                                                                                                                  |
| -------------------- | -------------- | --------------------------------------------------------------------------------------------------------------------------------------- |
| Argent               | Non (accroche) | Montants en entier XOF, informatifs. Un avenant change `Booking.amount_xof`, sans `LedgerEntry`. Registre de clôture posé, sans abonné. |
| KYC                  | Non            | —                                                                                                                                       |
| Machine à états      | **Oui**        | Toutes les transitions de l'étape 4 sont activées. Deux couples sont ajoutés : `en_route → cancelled` et `on_site → cancelled`.         |
| Auth, permissions    | Oui            | Nouveaux groupes d'admin `Médiation` et `Modération avis`. Un pro suspendu peut encore terminer une intervention en cours.              |
| Données personnelles | **Oui**        | Photos du logement (sans EXIF ni GPS), code de fin chiffré, textes de litige et d'avis jamais journalisés. Rétention fixée.             |

## Parcours

- **Pro (API ; en local, `demo_pro`).** « En route », puis « Arrivé », puis photos avant et « Commencer ». Au besoin, il propose un avenant. Ensuite, photos après, saisie du code que lui donne le client, et « Terminé ». Une action rejouée renvoie l'état courant.
- **Client (web, `/compte/demandes/[id]`).**
  - Pendant la mission : il suit l'étape en cours (actualisation) et voit son code de fin dès `scheduled`. Il le reçoit aussi par SMS au départ du pro, et peut le transmettre à un proche. Il accepte ou refuse un avenant et voit les photos. « Signaler un problème » reste visible pendant toute la mission.
  - Après le créneau et une marge, il peut déclarer « Le pro n'est pas venu ». Le message lui propose d'abord d'appeler le pro.
  - Après `completed` : « Tout va bien » propose l'avis sans l'exiger. « Signaler un problème » ouvre le litige jusqu'à la fin de la fenêtre.
- **Ops (admin Django).** Tranche les litiges et les no-shows contestés (groupe `Médiation`) et voit alors les photos. Joint le client par appel ou WhatsApp. Masque un avis (groupe `Modération avis`).
- **Système.** Envoie les rappels, clôt à la fin de la fenêtre, publie les avis, purge les photos et les repères à échéance.

## Réalité terrain

- **Réseau intermittent, sans app Pro hors ligne avant l'étape 6.** Les actions du pro sont idempotentes par état : rejouer `en-route` sur une réservation déjà `on_site` répond `200`, sans événement.
  - Elles rattrapent les étapes simples manquées : `arrive` depuis `scheduled` écrit `en_route` puis `on_site` (deux appels à `transition()`, métadonnée `chained`). `start` et `complete` ne sont jamais déduits.
  - Un `occurred_at` facultatif (heure de l'appareil, 24 h avant au plus, jamais dans le futur ni avant l'événement précédent) est gardé en métadonnée pour la future file hors ligne. L'heure du serveur fait foi.
- **Photos qui ne partent pas.** Elles sont indépendantes des transitions. `start` et `complete` exigent une photo de la phase **ou** `photos_pending: true` (la file de l'appareil les enverra plus tard). Seule exception : `client_refuses` (plus bas). L'envoi reste ouvert jusqu'à `closed`. Si aucune photo n'est arrivée à la clôture, un drapeau `before_photos_missing` ou `after_photos_missing` (sélecteur) est compté par pro pour l'Ops.
- **SMS métier.** Ce sont des types de `notifications.notify()`, sans passerelle nouvelle : adaptateur `log` en local, SMS réel au chantier prod. `notify()` ne transporte que le type et des `public_id`. Le futur adaptateur SMS rendra le gabarit (code, prix) côté serveur, à partir de la référence.
- **Code de fin sans réseau.**
  - Le code est affiché dès `scheduled` : la page chargée le matin reste lisible hors ligne.
  - Une notification SMS automatique part au passage à `en_route`, et le client peut en demander 2 de plus.
  - **Limite connue (diaspora).** Moussa ne reçoit pas de SMS local. Le client transmet lui-même le code à un proche, par exemple via WhatsApp (« Partager à un proche », lien construit dans le navigateur). La désignation formelle d'un proche est V3.
- **Littératie.** Une note et une puce font un avis complet ; le commentaire est vraiment facultatif. Chaque icône (étoiles, puces, motifs) porte un libellé.
- **Data.** Côté client, seules les miniatures WebP (environ 20 Ko) sont chargées par défaut. L'image pleine (1 600 px au plus, environ 200 Ko) ne se charge qu'à la demande.
- **Confiance.** L'avenant montre l'ancien et le nouveau prix ; aucun prix ne change sans un geste du client. Un avis n'est possible qu'après une vraie réservation terminée.

## Modèle de données et API

### Machine à états (`bookings.machine`)

| Couple                              | Acteur              | Exige / effets                                                                                                                      |
| ----------------------------------- | ------------------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| `scheduled → en_route`              | pro                 | `en_route_at` ; notification SMS du code de fin                                                                                     |
| `en_route → on_site`                | pro                 | `on_site_at`                                                                                                                        |
| `on_site → in_progress`             | pro                 | photo `before` ou `photos_pending` ; `started_at`                                                                                   |
| `in_progress → in_progress`         | client              | accepte un avenant : `amount_xof` prend le total de l'avenant, métadonnée `amendment`                                               |
| `in_progress → completed`           | pro                 | code valide, ou `no_code` + motif ; photo `after` (ou `photos_pending`, sauf `client_refuses`) ; `completed_at`, `dispute_deadline` |
| `completed → closed`                | system              | tâche `close_due` à `dispute_deadline` ; gestionnaires de clôture                                                                   |
| `completed → disputed`              | client              | avant `dispute_deadline` ; crée un `trust.Dispute`                                                                                  |
| `disputed → closed`                 | ops                 | décision journalisée ; gestionnaires de clôture                                                                                     |
| `en_route → cancelled` **(ajouté)** | client, pro, system | mêmes effets que `scheduled → cancelled` (`late` toujours vrai)                                                                     |
| `on_site → cancelled` **(ajouté)**  | pro, system         | pro : `client_absent` (poids 0, tracé), `job_mismatch`, `other`. Le client ne peut pas annuler un pro déjà sur place                |

- **No-show.** Il se déclare à partir de `slot_end` + `BOOKING_NO_SHOW_GRACE` (60 min), si la réservation est encore `scheduled` ou `en_route`.
  - L'écran propose d'abord « Appeler le pro », puis « Il n'est pas venu ».
  - La réservation passe à `cancelled` (acteur `client`, motif `pro_no_show`), avec les effets d'un désistement du pro : demande rouverte en `open` avec une nouvelle échéance, pro exclu.
  - Les autres devis, refusés à la confirmation, ne reviennent pas : leurs créneaux sont souvent passés. Le client lit « Votre demande est de nouveau visible des pros ».
  - Aucune annulation automatique : le pro est peut-être venu sans rien saisir. La tâche `no_show_check` interroge le client à la même heure.
- **Vérification du no-show (`bookings.NoShowReport`).** Champs : `booking` (OneToOne), `status` (`pending`, `contested`, `confirmed`, `dismissed`), `contest_note`, `decided_by`, `decided_at`.
  - Le pro conteste en un geste, avec une note (numéros refusés), dans les `BOOKING_NO_SHOW_CONTEST_WINDOW` (24 h).
  - Sans contestation, `confirm_no_shows` passe le rapport à `confirmed`, et c'est seulement alors que le poids **3** s'applique.
  - Un rapport contesté attend l'Ops (« Confirmer » ou « Écarter »). L'admin filtre les no-shows déclarés alors que `en_route_at` ou `on_site_at` existe.
  - L'exclusion du pro de la demande reste en place dans tous les cas.
- `reliability_weight` prend aussi le motif en compte. `_cancel` choisit les effets selon la partie fautive (`pro_no_show` est traité comme un désistement du pro), et non plus selon l'acteur seul.
- **Suspension d'un pro.** Elle annule ses réservations jusqu'à `on_site`. Une intervention `in_progress` peut encore être terminée (photos, code) par le gérant suspendu. Il n'a aucune autre écriture.
- `Booking.ACTIVE` est remplacé par deux ensembles : `ENGAGED` (de `accepted` à `disputed`, bloque la suppression du compte) et `CANCELLABLE` (de `accepted` à `on_site`).
- `Booking` : ajout de `original_amount_xof`, `en_route_at`, `on_site_at`, `started_at`, `completed_at`, `closed_at`, `dispute_deadline`, `dispute_reminder_sent_at`, `completion_method` (`code`, `no_code`), `no_code_reason`, `completion_code_enc`, `completion_code_attempts`, `completion_code_locked`, `completion_code_regenerations`, `completion_code_sms_sent`. Clés ajoutées au schéma fermé de `BookingEvent.metadata` : `chained`, `occurred_at`, `amendment`, `photos_pending`, `completion_method`, `dispute_decision`.

### Code de fin

- **Génération et stockage.** 4 chiffres (`secrets.randbelow`), générés au passage à `scheduled`. Le code est chiffré (MultiFernet, nouvelle clé `DATA_ENCRYPTION_KEYS` vérifiée au démarrage), comparé en temps constant, puis effacé à `completed` ou à `cancelled`.
- **Affichage.** Visible du client seul (champ `completion_code`, de `scheduled` à `in_progress`), avec une ligne : « Ne donnez le code qu'à la fin, quand le travail vous convient ». Il n'apparaît jamais dans une réponse au pro, un log, un audit, Sentry ou une URL. Le pro l'envoie dans le corps de la requête.
- **Notification SMS `completion_code.sms`.** 1 envoi automatique à `en_route`, plus 2 envois sur demande du client (`429 sms_limit_reached` au-delà).
- **Essais limités.** Après 5 codes faux, le code est verrouillé (`409 completion_code_locked`). Chaque échec est audité, sans le code. Le client peut régénérer son code 3 fois : nouveau code, compteur d'essais remis à zéro.
- **Repli `no_code`.** `complete` accepte un `no_code_reason` : `client_absent`, `client_no_phone`, `code_locked` ou `client_refuses` (client présent qui refuse de donner le code). Avec `client_refuses`, une photo `after` au moins est obligatoire (`photos_pending` refusé). La fenêtre de contestation passe à 72 h au lieu de 48 h, et le client est notifié. La part de fins `no_code` par pro est visible de l'Ops.

### Photos (`bookings.BookingPhoto`, ADR 0011)

`booking` · `phase` (`before`, `after`) · `status` (`processing`, `ready`, `failed`) · `image_key` · `thumb_key` · `width`, `height`, `size_bytes` · `taken_at` (déclarée, facultative) · `idempotency_key` (unique par réservation) · `hidden_at`, `hidden_by` · `purged_at`.

- **Envoi.** Multipart par l'API, par le gérant seul, de `on_site` à `disputed`. JPEG, PNG ou WebP, 8 Mo au plus, de 1 à 5 photos par phase, `Idempotency-Key` obligatoire. Consigne fixe côté pro : « Photographiez seulement le travail, pas les personnes. »
- **Traitement dans la requête.** Pillow vérifie l'image, la redresse (`exif_transpose`), la réduit à 1 600 px et la réencode en WebP q75 **sans aucune métadonnée**. L'original et son GPS ne sont jamais stockés. La tâche `make_thumbnail` (400 px, idempotente) produit ensuite la miniature.
- **Lecture.** URL signées valables 10 min, pour le client et le gérant de la réservation. L'Ops ne les voit que dans l'admin et seulement si un litige existe ; chaque consultation est auditée. Les clés d'objet ne contiennent que des `public_id`.
- **Signalement.** « Signaler cette photo », côté client, la masque (`hidden_at`, audit) pour le client et le pro. L'Ops la garde pour un litige et peut la réafficher.
- **Rétention.** Mention affichée au client : « gardées 12 mois, puis supprimées ». Les photos sont gardées 12 mois après `closed` ; ensuite, les objets sont supprimés et la ligne reçoit `purged_at`. À la suppression du compte (client ou gérant), les objets sont supprimés après commit. Le repère et la position de la demande sont vidés 90 jours après `closed` : c'est le point laissé ouvert par la spec 003.

### Avenants (`bookings.Amendment`, `AmendmentLine`)

`booking` · `status` (`proposed`, `accepted`, `declined`, `withdrawn`, `lapsed`) · `reason` (`visit_diagnosis`, `extra_work`, `parts`, `other` + note) · `previous_amount_xof` · `total_xof` · lignes (mêmes règles que `QuoteLine`, de 1 à 8) · `idempotency_key` · `decided_at`.

- **Proposition.** En `in_progress` seulement. Le pro propose le **nouveau prix complet** : une visite déductible n'y figure pas.
  - Règles : `0 < total ≤ QUOTE_MAX_XOF`, total différent du montant courant, un seul avenant `proposed` à la fois (contrainte partielle), 3 propositions au plus par réservation.
  - Notification SMS `amendment.proposed` au client : l'ancien et le nouveau prix en XOF, sans aucune autre donnée.
- **Décision, depuis la session du client seulement** (jamais par le pro, ni par un lien SMS).
  - S'il accepte : `transition(in_progress → in_progress)` est appelée, et `amount_xof` mis à jour dans la même transaction, avec un audit.
  - S'il refuse : l'avenant passe à `declined`, et le travail continue au prix courant.
  - Le pro peut retirer son avenant. `complete` passe à `lapsed` un avenant encore en attente.
- **Carte côté client.** Le nouveau montant en gros chiffres, l'ancien prix, l'écart en %, les lignes et le motif, avec la phrase « Vous ne payez pas plus tant que vous n'avez pas accepté ». Une hausse au-delà de `AMENDMENT_CONFIRM_THRESHOLD_PCT` (50) demande une confirmation supplémentaire ; une baisse n'en demande aucune.

### Clôture et litige (`trust.Dispute`)

- **Clôture.** `close_due` (beat, toutes les 5 min, idempotente) passe à `closed` les réservations `completed` dont `dispute_deadline` est dépassée (motif `window_elapsed`). Une notification SMS `booking.dispute_reminder` part 12 h avant l'échéance (`dispute_reminder_sent_at`).
- **Litige.** `POST dispute/` avant l'échéance, avec un motif (`not_done`, `poor_quality`, `damage`, `price`, `behaviour`, `other`) et un texte de 10 à 1 000 caractères. L'écran le dit : « Jeflink examine et décide. Pas de remboursement pour l'instant. » Avant `completed`, « Signaler un problème » ouvre le WhatsApp du support, avec la référence de la réservation.
- **Modèle `trust.Dispute`** : `booking` (OneToOne), `reason`, `description`, `status` (`open`, `resolved`), `decision` (`for_client`, `for_pro`, `no_fault`), `decision_note`, `resolved_by`, `resolved_at`. L'Ops joint le client par appel ou WhatsApp avant de trancher.
- **Effets d'une décision `for_client`.** Le pro est averti (`dispute.decided`), un poids de fiabilité 2 est journalisé sur l'événement `disputed → closed`, et l'avis reste possible 7 jours après la décision.
- **Pourquoi dans `trust`, et pas une table de `bookings`.** ARCHITECTURE.md y range déjà litiges et garantie. La reprise sous 7 jours, le remboursement (V2) et l'IA6 s'y grefferont ; une table dans `bookings` serait à migrer plus tard.
  - Les appels vont dans un seul sens : `bookings.services` appelle `trust.services`, jamais l'inverse.
  - L'action d'admin « Trancher » appelle `bookings.services.resolve_dispute`. Celle-ci fait `disputed → closed` (acteur `ops`, motif `dispute_<decision>`), puis appelle `trust.services.record_decision` et écrit un audit. Aucun remboursement en V1.
- **Point d'accroche pour l'étape 5.** `bookings.services.register_close_handler(fn)` est appelé dans la transaction de toute arrivée à `closed`, avec `(booking, reason)`.
  - `reviews` s'y inscrit pour publier les avis.
  - `wallet` s'y inscrira pour écrire `pro_commission_due` sur `amount_xof`, de façon idempotente par réservation. Il recevra la décision du litige, `for_client` comprise.

### Avis (`reviews`)

`Review` (`BaseModel`) : `booking` (OneToOne) · `provider` · `author` · `rating` (de 1 à 5, `CheckConstraint`) · `tags` (`ArrayField` de codes : `on_time`, `quality`, `clean`, `price_kept`, et sous 3 étoiles `late`, `redo_needed`, `messy`, `price_changed`) · `comment` (500 caractères, facultatif, numéros masqués à l'affichage) · `published_at` · `edited_at` · `hidden_at`, `hidden_reason`, `hidden_by`.

- **Qui et quand.** Seul le client de la réservation, de `completed` à `completed_at` + 14 jours, `disputed` compris. L'avis reste modifiable dans ce délai (`PUT`, un seul avis par réservation). Seule la note est exigée.
- **Proposé, jamais exigé.** « Tout va bien » est un simple geste d'écran, sans appel à l'API : il propose l'avis. La clôture ne dépend jamais de l'avis.
- **Publication.** À la clôture (gestionnaire), ou tout de suite si la réservation est déjà `closed`. Ainsi, le pro ne voit pas l'avis tant qu'il peut encore faire pression.
- **Moyenne.** `reviews.selectors.rating_for_providers` calcule la moyenne et le nombre des avis publiés et non masqués, hors comptes de revue et pros de démo. Elle est annotée sur les devis et la réservation. Champ `rating {average (1 décimale), count}` ajouté à `ClientProviderSerializer`. Il vaut `null` sous 3 avis, et le front affiche « Nouveau sur Jeflink ».
- **Modération.** L'Ops masque ou réaffiche un avis (motif, audit), sans jamais le supprimer. À la suppression du compte du client : commentaire vidé, auteur détaché, note gardée.
- **Pas d'avis du pro sur le client ici.** Il viendra à l'étape 6, avec l'app Pro. Le motif `client_absent` trace déjà le cas grave.

### Endpoints

Tags existants (`bookings`, `pro`). Un objet d'un autre utilisateur répond `404`. Un rejeu idempotent répond `200`.

| Méthode | Chemin                                                                      | Permission                                     | Notes                                                                                                                                               |
| ------- | --------------------------------------------------------------------------- | ---------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------- |
| POST    | `/api/pro/bookings/{id}/en-route/`, `/arrive/`                              | `IsVerifiedPro` + `IsProOwner`                 | `{occurred_at?}`                                                                                                                                    |
| POST    | `/api/pro/bookings/{id}/start/`                                             | `IsVerifiedPro` + `IsProOwner`                 | `{photos_pending?, occurred_at?}` ; `422 before_photos_required`                                                                                    |
| POST    | `/api/pro/bookings/{id}/complete/`                                          | `HasOwnerRole` + `IsProOwner` (suspendu admis) | `{code` ou `no_code_reason, photos_pending?, occurred_at?}` ; `422 completion_code_invalid`, `after_photos_required` ; `409 completion_code_locked` |
| POST    | `/api/pro/bookings/{id}/photos/`                                            | comme `complete`                               | multipart `{phase, file, taken_at?}`, `Idempotency-Key` ; `422 photo_invalid`, `413 photo_too_large`, `409 photo_limit_reached`                     |
| POST    | `/api/pro/bookings/{id}/amendments/` · `/api/pro/amendments/{id}/withdraw/` | `IsVerifiedPro` + `IsProOwner`                 | `Idempotency-Key` ; `409 amendment_pending`, `amendment_limit` ; `422 amendment_total_invalid`                                                      |
| POST    | `/api/pro/bookings/{id}/cancel/`                                            | inchangée                                      | ajout du motif `client_absent` (à `on_site`)                                                                                                        |
| POST    | `/api/pro/bookings/{id}/contest-no-show/`                                   | `HasOwnerRole` + `IsProOwner`                  | `{note}` ; `409 no_show_contest_closed` ; `422 note_invalid`                                                                                        |
| POST    | `/api/bookings/{id}/amendments/{aid}/accept/`, `/decline/`                  | `IsClient`                                     | `409 amendment_not_pending`                                                                                                                         |
| POST    | `/api/bookings/{id}/completion-code/regenerate/`, `/sms/`                   | `IsClient`                                     | `409 completion_code_regen_limit` ; `429 sms_limit_reached`                                                                                         |
| POST    | `/api/bookings/{id}/photos/{pid}/report/`                                   | `IsClient`                                     | masque la photo ; rejeu `200`                                                                                                                       |
| POST    | `/api/bookings/{id}/no-show/`                                               | `IsClient`                                     | `409 no_show_too_early`                                                                                                                             |
| POST    | `/api/bookings/{id}/dispute/`                                               | `IsClient`                                     | `409 dispute_window_closed` ; `422 reason_invalid`                                                                                                  |
| PUT     | `/api/bookings/{id}/review/`                                                | `IsClient`                                     | `409 review_window_closed`, `review_not_allowed` ; `422 review_invalid`                                                                             |

- **Lecture d'une réservation (client et pro).** Ajouts : étapes horodatées, `photos[]` (`thumb_url`, `url`, `expires_at`), `amendments[]`, `dispute_deadline`, `completion_method`. Côté client seulement : `completion_code`, `review`, `can_*`. Côté pro : l'avis une fois publié, l'état du no-show. Le détail d'une demande embarque cette réservation étendue : toujours un seul appel.
- **Notifications** (type et `public_id` seulement) :
  - avec un SMS : `completion_code.sms`, `amendment.proposed`, `booking.dispute_reminder` ;
  - les autres : `booking.progress`, `amendment.decided`, `booking.completed`, `booking.no_show_check`, `no_show.contested`, `booking.disputed`, `dispute.decided`, `booking.closed`.
- **Réglages**, jamais en dur :
  - no-show : `BOOKING_NO_SHOW_GRACE` (60 min), `BOOKING_NO_SHOW_CONTEST_WINDOW` (24 h) ;
  - contestation : `BOOKING_DISPUTE_WINDOW` (48 h) et `…_NO_CODE` (72 h), `BOOKING_DISPUTE_REMINDER` (12 h avant) ;
  - code de fin : `COMPLETION_CODE_*` (4 chiffres, 5 essais, 3 régénérations, 1 SMS automatique et 2 sur demande) ;
  - photos : `BOOKING_PHOTO_*` (8 Mo, 1 600 px, de 1 à 5 par phase, 12 mois) ;
  - avenants : `BOOKING_AMENDMENTS_MAX` (3), `AMENDMENT_CONFIRM_THRESHOLD_PCT` (50) ;
  - divers : `BOOKING_CONTACT_RETENTION` (90 j), `REVIEW_WINDOW` (14 j), `REVIEWS_MIN_DISPLAY` (3), `OCCURRED_AT_MAX_SKEW` (24 h).

## Points de sécurité

- Code de fin : chiffré, comparé en temps constant, 5 essais. Absent des réponses au pro, des logs (adaptateur `log` compris), des audits et des URL : un test le cherche dans les logs capturés et dans les audits.
- Photos réencodées avant tout stockage : un test vérifie qu'un JPEG avec GPS ressort sans EXIF. Le type est vérifié par décodage, pas par l'extension, et la taille décodée est bornée (`MAX_IMAGE_PIXELS`).
- Bucket privé et URL signées courtes, sans URL publique permanente. Les clés d'objet ne portent aucune donnée personnelle.
- `amount_xof` n'est écrit que par `accept_amendment`, sous verrou, depuis la session du client. Le test d'architecture est étendu à `amount_xof`.
- Avis : un seul par réservation terminée, et l'auteur doit être le client. Comptes de revue et pros de démo sont exclus des moyennes.
- Admin : groupes dédiés. Décisions (litige, no-show) et consultation des photos sont auditées. Les textes du litige et de la contestation ne sont jamais journalisés.
- Un pro suspendu n'a que `complete` et l'envoi de photos, sur une intervention `in_progress`.
- Revue `security-reviewer` une fois sur la feature (tâches [sécu]).

## IA (si applicable)

Aucune. L'IA6 (résumé de litige) lira plus tard le litige, les photos et les avenants.

## Hors périmètre

- Argent : commission, paiement, remboursement, séquestre, reprise gratuite sous 7 jours (étape 5, V2).
- **Techniciens : reportés à l'étape 6 (app Pro).** Le gérant reste son propre technicien, et `IsTechnicianAssigned` refuse toujours. Sans app Pro, un technicien n'a aucun moyen d'agir ; l'affectation se testera avec la vraie liste de missions.
- Position « en route » en direct, Channels, push, app Pro hors ligne (étape 6).
- Avis vocal (backlog de l'étape 6). Avis du pro sur le client, réponse du pro à un avis, profil public du pro.
- Photos du client pour un litige, messagerie ; désignation formelle d'un proche qui reçoit le code (diaspora, V3).
- Console Ops : l'admin Django suffit pour l'instant.

## Critères d'acceptation

- [ ] En local, de bout en bout : avec `demo_pro`, une réservation `scheduled` passe par `en-route` (notification `completion_code.sms` dans le journal, sans le code), puis `arrive` et `start` (photo factice). Un avenant que Zay accepte sur le web change le montant. Puis `complete` avec le code lu sur le web. La réservation est close par `close_due`, et l'avis apparaît sur les devis de ce pro à partir de 3 avis.
- [ ] Chaque couple de la machine est testé (actif, interdit). Chaque transition écrit un `BookingEvent`. Le rattrapage écrit un événement par étape. Rejouer une action ne crée aucun événement.
- [ ] Après 5 codes faux, le code est verrouillé. Une régénération le débloque. Le code n'apparaît dans aucun log, audit ni réponse au pro. `client_refuses` sans photo après répond `422`.
- [ ] Une photo avec EXIF GPS est stockée sans métadonnée. Un envoi rejoué ne crée pas de deuxième photo. `start` sans photo et sans `photos_pending` répond `422`. Une photo signalée disparaît des deux vues.
- [ ] Le no-show n'est possible qu'après `slot_end` + marge. Il rouvre la demande et exclut le pro. Le poids 3 ne s'applique qu'après 24 h sans contestation, ou après une confirmation de l'Ops.
- [ ] Un litige, tranché dans l'admin, clôt la réservation avec une décision journalisée. Les gestionnaires de clôture sont appelés une seule fois (test avec un gestionnaire factice). Le rappel part une seule fois.
- [ ] Un avis est refusé sans réservation terminée, hors délai ou d'un autre compte. Une note seule est acceptée. Un avis masqué sort de la moyenne.
- [ ] Les anonymiseurs (photos, avis, litiges, no-shows) et la purge sont testés. `make openapi` est à jour, le client TS régénéré, les clés i18n `fr` présentes.

## Tâches par couche

Chacune livrable et testable seule, dans l'ordre. `make openapi` à chaque tâche qui touche l'API.

- api :
  1. **Stockage (ADR 0011)** : `django-storages[s3]` et Pillow, `common.storage` (stockage `photos`, `signed_url`), `common.images.reencode` (sans métadonnée), `InMemoryStorage` en test, commande locale `ensure_bucket`, réglages `S3_*` et contrôle au démarrage. Tests de réencodage (GPS retiré, orientation, image piégée).
     - Fait : `django-storages[s3]` 1.14 et Pillow 12 ; `common.storage` (`put`, `read`, `delete`, `signed_url`), `common.images.reencode` (WebP sans métadonnée, `IMAGE_MAX_PIXELS`), `ensure_bucket` (`make bucket`, lancé par `make up`), réglages `S3_*`, contrôle au démarrage hors local. En test, `InMemoryStorage` vidé entre les tests.
  2. [sécu] **Machine** : couples activés et ajoutés, rattrapage, `occurred_at`, horodatages, `ENGAGED` et `CANCELLABLE`, `client_absent`, règle de suspension, `register_close_handler`, `close_due`, rappel de contestation, endpoints `en-route`, `arrive`, `start`. Tests exhaustifs des couples.
     - Fait : tous les couples sont actifs (dont `en_route → cancelled` et `on_site → cancelled`), `transition()` pose les horodatages et la fenêtre de contestation et accepte `metadata` et `fields`, `ENGAGED` et `CANCELLABLE`, `client_absent` (poids 0), suspension jusqu'à `on_site`, `register_close_handler`, tâches `close_due` et `remind_disputes` (beat), endpoints `en-route`, `arrive`, `start` (`start` exige `photos_pending` tant que les photos n'existent pas : branché à la tâche 5). Migration `bookings.0003` (horodatages, `original_amount_xof` rempli depuis `amount_xof`).
  3. [sécu] **No-show** : déclaration après la marge, `NoShowReport`, contestation du pro, `confirm_no_shows`, actions d'admin « Confirmer » et « Écarter », filtre `en_route_at`/`on_site_at`, poids différé, `no_show_check`.
     - Fait : `NoShowReport` (+ `Booking.no_show_check_sent_at`), `declare_no_show` (marge `BOOKING_NO_SHOW_GRACE`, effets d'un désistement du pro, poids 0 à la déclaration), `contest_no_show` (note sans numéro, 24 h), `confirm_no_shows` (poids 3 journalisé dans l'audit `bookings.no_show.decided`), `decide_no_show`, tâches `confirm_no_shows` et `no_show_check` (beat), admin « Médiation » (groupe créé par la migration `bookings.0005`) avec filtre « départ ou arrivée saisis ». Endpoints `POST /api/bookings/{id}/no-show/` et `POST /api/pro/bookings/{id}/contest-no-show/`.
  4. [sécu] **Code de fin** : `DATA_ENCRYPTION_KEYS` (`.env.example` et docker-compose de dev, valeur factice), génération à `scheduled`, `complete` (code ou `no_code`, dont `client_refuses`), verrou, régénération, notification SMS (automatique et sur demande), champ client. Test d'absence dans les logs et les audits.
     - Fait : `DATA_ENCRYPTION_KEYS` (`common.crypto`, MultiFernet, contrôle au démarrage, clé factice dans docker-compose et les tests, valeur vide dans `.env.example`, allowlist gitleaks), code généré à `scheduled` (migration de rattrapage des missions en cours) et effacé à `completed`/`cancelled`, `complete_work` (essais comptés même sur erreur, verrou à 5, `no_code` dont `client_refuses`, fenêtre de 72 h), régénération (3 fois) et SMS (`429 sms_limit_reached`), champs client `completion_code`, `completion_code_locked`, `can_regenerate_completion_code`, `can_send_completion_code_sms`, part de fins sans code par pro dans l'admin des pros. Écart : un code mal formé (pas 4 chiffres ASCII) répond `completion_code_invalid` sans compter d'essai.
  5. **Photos** : `BookingPhoto`, envoi idempotent, limites, `make_thumbnail`, URL signées dans les deux sérialiseurs, signalement par le client, purge à 12 mois, anonymiseur, `BOOKING_CONTACT_RETENTION`.
     - Fait : `BookingPhoto`, `upload_photo` (multipart, `Idempotency-Key`, réencodage dans la requête, rien ne reste dans le stockage si la base refuse), `make_thumbnail` (Celery, idempotente), `photos[]` (`thumb_url`, `url`, `expires_at`) dans les deux sérialiseurs, `report_photo`, tâches `purge_photos` et `purge_contact` (quotidiennes), anonymiseur (objets supprimés après commit), drapeaux `missing_photos` dans l'admin des pros, `start` et `complete` branchés sur les vraies photos. Écarts : (1) l'envoi est refusé à `closed` (`409 transition_not_allowed`), la spec disant à la fois « jusqu'à `disputed` » et « jusqu'à `closed` » ; (2) la contrainte `request_landmark_or_location` ne vise plus les demandes `booked` (migration `requests.0004`), faute de quoi le repère d'une demande réservée n'aurait pas pu être vidé 90 jours après la clôture ; (3) tant que la miniature se prépare, `thumb_url` vaut l'image pleine.
  6. **Avenants** : modèles, proposition et notification SMS, retrait, acceptation (transition et montant), refus, `lapsed`, endpoints, tests de plafond et de concurrence.
  7. [sécu] **Litiges** (`trust.Dispute`) : ouverture, `resolve_dispute` et effets de `for_client`, admin « Trancher » (groupe `Médiation`, migration), photos dans l'admin avec audit, schémas d'audit, anonymiseur.
  8. **`reviews`** : domaine, `PUT`, publication par le gestionnaire de clôture, `rating_for_providers`, `rating` sur les devis et la réservation, admin « Masquer » (groupe `Modération avis`), anonymiseur.
  9. **Notifications** : les 11 nouveaux types, branchés et testés (type et `public_id` seulement).
  10. **Démo** : `demo_pro en-route|arrive|start|photo|amend|complete|cancel|contest` (photo factice générée avec un EXIF GPS, `--code` ou `--no-code`), `DJANGO_ENV=local` seulement.
  11. **Documentation** : ARCHITECTURE.md (diagramme et domaines), `apps/api/CLAUDE.md`, `chantier-prod.md`.
- web (conventions de la spec 003 : `app/compte/demandes/`, `lib/requests/`, Server Actions, BFF) :
  1. **Suivi** : frise des étapes, `RefreshButton`, et actualisation toutes les 60 s quand l'onglet est visible et la mission en cours. Carte du code de fin : chiffres lisibles, avertissement d'une ligne, SMS, « Partager à un proche », régénération. « Signaler un problème » toujours visible. No-show après la marge, avec « Appeler le pro » d'abord. Nouveau dossier `lib/bookings/` (étapes, actions permises).
  2. **Photos et avenant** : miniatures seules par défaut (`next/image`, `unoptimized`, hôte S3 dans `remotePatterns`), « Signaler cette photo », mention de rétention. Carte d'avenant (gros montant, phrase « Vous ne payez pas plus… »), Accepter ou Refuser, confirmation au-delà du seuil.
  3. **Fin** : « Tout va bien » propose l'avis (étoiles et puces avec libellé, commentaire facultatif). Litige jusqu'à HH:MM (Dakar), avec « Jeflink examine et décide. Pas de remboursement pour l'instant. » Note ou « Nouveau sur Jeflink » sur les cartes de devis.
  4. **i18n et revue** : espace `bookings` en `fr`, codes d'erreur testés contre la liste de l'API, revue `design-guardian`.
- console : rien (admin Django). client / pro : rien (étape 6) ; le client TS régénéré suffit.

## Questions à trancher (Zay)

✅ Q1 à Q7 acceptées par Zay le 2026-10-03, avec les ajustements terrain intégrés ci-dessus.

1. **Code de fin** : 4 chiffres, visible dès `scheduled`, avec un avertissement d'une ligne ; notification SMS automatique à `en_route`, 2 de plus sur demande ; partage à un proche. _Proposition : oui. Terrain : accepté, avec le SMS automatique à `en_route`._
2. **Fin sans code** : 4 motifs, dont `client_refuses` qui exige une photo après ; contestation sur 72 h ; part par pro suivie par l'Ops. _Proposition : oui. Terrain : accepté, avec `client_refuses` et photo obligatoire._
3. **No-show** : déclaré par le client après `slot_end` + 60 min, « Appeler le pro » d'abord. Contestation du pro sous 24 h, poids 3 appliqué ensuite seulement. Deux couples ajoutés à la machine. _Proposition : oui. Terrain : accepté, avec marge, contestation et poids différé._
4. **Avenant** : nouveau prix complet, plafond `QUOTE_MAX_XOF`, 3 propositions, notification SMS des deux prix, acceptation depuis la session du client seulement, confirmation au-delà de `AMENDMENT_CONFIRM_THRESHOLD_PCT` (50), aucune pour une baisse. _Proposition : oui. Terrain : accepté avec ces ajustements._
5. **Photos** : envoi par l'API (ADR 0011), de 1 à 5 par phase, consigne « pas les personnes », signalement par le client, 12 mois puis suppression ; repère et position vidés 90 jours après la clôture. _Proposition : oui. Terrain : accepté avec ces ajustements._
6. **Avis** : une note suffit, puces avec libellé, proposé mais jamais exigé, publié à la clôture, affiché à partir de 3 avis. Pas d'avis du pro sur le client avant l'étape 6. _Proposition : oui. Terrain : accepté, avis vocal au backlog de l'étape 6._
7. **Litiges dans `trust`**, tranchés dans l'admin après un appel au client, sans remboursement ; `for_client` a des effets visibles ; rappel SMS 12 h avant l'échéance ; techniciens reportés à l'étape 6. _Proposition : oui. Terrain : accepté avec ces ajustements._
