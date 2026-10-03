# Spec 003 — Demande, devis, réservation

Statut : validée · 2026-10-03 (Zay) · ADR lié : 0010 (demande et réservation, accepté) · Revue `terrain-reviewer` intégrée (Q1 à Q7 acceptées, Q2 et Q4 ajustées)

## Problème

Awa a une fuite à Ouakam et veut un pro fiable, vite, à un prix connu d'avance. Ibou, électricien solo, veut des clients sans démarcher. C'est le cœur de la V1 (PRODUCT.md §6) : le client décrit son besoin, au plus 3 pros vérifiés envoient un devis, le client en choisit un, le pro confirme le créneau. Cette spec s'arrête à la réservation planifiée (`scheduled`) et aux annulations. Le reste du cycle (`en_route` → `closed`) est l'étape 4.

| Zone sensible        | Touchée ? | Détail                                                                                                                        |
| -------------------- | --------- | ----------------------------------------------------------------------------------------------------------------------------- |
| Argent               | Non       | Montants de devis en entier XOF, informatifs. Aucun paiement, aucun `LedgerEntry` (portefeuille et commission : étape 5).     |
| KYC                  | Non       | Vérification manuelle d'un pro par un statut dans l'admin. Aucune pièce, aucun selfie. Le vrai KYC viendra avec `trust`.      |
| Machine à états      | **Oui**   | `Booking` et `transition()` posés. Actives : création à `accepted`, `accepted → scheduled`, `accepted/scheduled → cancelled`. |
| Auth, permissions    | Oui       | `IsVerifiedPro` ajouté, `IsProOwner` remplacé (objet). `IsTechnicianAssigned` reste refusé par défaut (étape 4).              |
| Données personnelles | Oui       | Repère, position, téléphones : divulgués au seul pro confirmé, à `scheduled`. Jamais dans un log, un audit ou une URL.        |

## Parcours

- **Client (web).** « Faire une demande » : métier, service (facultatif), quartier (liste, texte libre ou « Utiliser ma position »), repère ou position, description, urgence, quand (« dès que possible » ou un jour et une plage : matin, après-midi, soir). Il suit ses demandes dans « Mes demandes » et compare jusqu'à 3 devis. Il en accepte un, et la page affiche « Le pro a jusqu'à HH:MM ; sinon vous retrouvez vos autres devis » (heure de Dakar, sans compte à rebours). Une fois le pro confirmé, elle affiche le créneau, le nom et le numéro du pro (appel et WhatsApp). Il peut annuler avec un motif. Si son quartier est inconnu, il lit « Nous vérifions votre quartier », avec le lien WhatsApp du support.
- **Pro (API ; en local : commande de démo).** Il voit les « demandes pour moi » (son métier, ses zones), sans numéro ni repère. Il envoie un devis ou le retire. À l'acceptation, il confirme (→ `scheduled`) et reçoit alors le repère, la position et le numéro du client. Il peut se désister, avec un motif.
- **Ops (admin Django).** Crée un pro (`manage.py onboard_provider`), le vérifie ou le suspend, rattache à une zone une demande au quartier inconnu, consulte les demandes non servies et le compteur de masquages par pro.

## Réalité terrain

- **Réseau.** Le détail d'une demande embarque ses devis (3 au plus) et sa réservation active : un seul appel. `Idempotency-Key` sur chaque création. Listes paginées par curseur. Le formulaire web survit à une coupure (web 1).
- **Adressage.** Repère en texte ou position, au moins l'un des deux. Un quartier inconnu ne bloque jamais : la demande passe en `needs_zone` et l'Ops la rattache (spec 002). Si la position tombe dans plusieurs zones, le client choisit (`zone_ambiguous`).
- **Confiance.** Seuls des pros vérifiés devisent, 3 devis au plus (pas de course au moins-disant), prix affiché avant le choix, confirmation explicite du pro, désistements tracés.
- **Contournement : une limite assumée.** Avant `scheduled`, les numéros saisis dans une description ou un message de devis sont masqués à l'affichage pour l'autre partie (motifs de `common.pii`). Le texte stocké reste intact. Ce masquage ne sera jamais étanche : chiffres en lettres, en wolof, espacés. On s'en tient donc à trois choses :
  - (a) la mention « Les coordonnées sont partagées après confirmation » sur l'écran des devis ;
  - (b) un compteur de masquages par pro (`Provider.masked_numbers_count`, sans le texte), visible de l'Ops pour repérer les abus ;
  - (c) le constat qu'une V1 sans paiement en ligne fuit de toute façon. Ce qui fait rester, c'est l'avis, le badge « Pro vérifié » et la re-réservation (étape 4), pas le masquage.
- **Paiement.** Mention fixe sur la réservation : « À régler au pro, en espèces ou par mobile money. Jeflink ne garde aucun argent pour l'instant. »
- **Langues.** Codes d'erreur, motifs et mentions fixes en clés i18n courtes (`fr` ; `wo` vide retombe sur `fr`). La description est libre, en français ou en wolof.

## Modèle de données et API

### `providers` (minimal)

`Provider` (`BaseModel`) : `owner` (FK `User`, une seule fiche par gérant) · `business_name` (60) · `trades` (M2M `catalog.Trade`) · `zones` (M2M `zones.Zone`) · `status` (`pending`, `verified`, `suspended`) · `status_changed_at` · `masked_numbers_count` · `is_demo` (booléen, `local`/`test` seulement, vérifié au démarrage).

- **Création** : `providers.services.onboard_provider(user, business_name, trades, zones, operator)` crée la fiche en `pending` et accorde le rôle `owner` (`accounts.services.grant_role`, motif `provider_onboarded`). Elle est exposée par `manage.py onboard_provider --phone … --name … --trades … --zones … --operator …`. L'inscription « Devenir pro » en libre-service viendra avec l'app Pro (étape 6). Les premiers pros sont recrutés sur le terrain (PRODUCT.md §9).
- **Vérification** : actions d'admin « Vérifier » et « Suspendre », réservées au groupe `Validation pros` (migration ; compte technique, comme `Saisie catalogue`). Elles passent par `providers.services.set_status()` et écrivent un `AuditEvent` (`providers.status.changed`, schéma déclaré). Une suspension retire les devis `submitted` et annule les réservations actives (acteur `system`, motif `provider_suspended`).
- **Techniciens : reportés à l'étape 4.** L'artisan solo est son propre technicien (ADR 0003). L'affectation n'a de sens qu'à `en_route` et `on_site`. Aucun `register_invitation_handler` ici : les invitations restent en `503 invitation_unavailable`.
- **Permissions** : `IsVerifiedPro` (`HasOwnerRole` + fiche `verified`) pour voir les demandes et deviser. `IsProOwner` devient une classe objet : `obj.provider.owner_id == user.id`. Une fiche suspendue lit encore ses réservations, mais n'écrit plus.

### `requests`

`ServiceRequest` : `client` · `trade` (FK `PROTECT`) · `service` (FK nulle, du même métier) · `zone` (FK nulle seulement en `needs_zone`) · `zone_text` (40, normalisé par `unknown_zone_text`, en `needs_zone` seulement) · `landmark` (300) · `location` (`PointField` nul ; `CheckConstraint` : repère ou position) · `description` (1 000 ; facultative si un service est choisi, sinon 3 caractères au moins) · `urgent` (défaut : `Service.urgent`) · `preferred_when` (`asap`, `date`) · `preferred_date` · `preferred_period` (`morning`, `afternoon`, `evening`, `any`) · `status` · `expires_at` (posé au passage en `open`) · `channel` (`web`, `app`, `whatsapp`) · `idempotency_key` + `payload_hash` (unique par client) · `first_quoted_at` · `closed_at` · `close_reason`.

| De → vers                                  | Déclencheur                                                                                  |
| ------------------------------------------ | -------------------------------------------------------------------------------------------- |
| création → `open` ou `needs_zone`          | `create_request` (`needs_zone` si `availability` = `zone_unknown`)                           |
| `needs_zone` → `open`                      | Ops : action d'admin « Rattacher à une zone » (groupe `Saisie catalogue`, `AuditEvent`)      |
| `open` → `quoted` → `open`                 | 1er devis actif / plus aucun devis actif (retrait, expiration)                               |
| `quoted` → `booked`                        | devis accepté                                                                                |
| `booked` → `quoted` ou `open`              | réservation annulée **par le pro ou le système** (désistement, non-confirmation, suspension) |
| `booked` → `cancelled`                     | réservation annulée par le client                                                            |
| `needs_zone`/`open`/`quoted` → `cancelled` | client (motif) ; `open`/`quoted` → `expired` : tâche à `expires_at`                          |

- **Création** : `create_request(*, client, draft: RequestDraft, channel, idempotency_key)`. La zone vient de `zone_slug`, sinon de `zone_text`, sinon de `location`, résolue par `zones.selectors.availability()`. `location` reste facultative à côté d'un slug. Issues :
  - `available` → `open` ;
  - `zone_unknown` → `needs_zone` ;
  - `zone_ambiguous` → `422` avec `candidates[{slug, name}]`, rien n'est créé, le client choisit ;
  - `trade_not_in_zone`, `out_of_area` → `422`, signal non servi, et le front propose WhatsApp (Q5) ;
  - `trade_not_found`, `trade_inactive`, `zone_not_found`, `zone_inactive` → `422`.
- **Limites** : 3 demandes non closes par client (`409 request_limit_reached`), et 10 créations par 24 h (limite par utilisateur, fermée si Redis tombe). Expiration 72 h après le passage en `open`, 24 h si urgente. Le temps passé en `needs_zone` ne compte pas. Toutes les durées de cette spec sont des réglages (`settings`), jamais en dur.
- **Demande non servie (IA7)** : émise ici, par `analytics.services.record_unserved()`. `analytics` naît avec un seul modèle, `UnservedDemand`, au schéma de la spec 002, sans identifiant d'utilisateur, en lecture seule dans l'admin. Motifs : ceux d'`availability` (sauf `zone_ambiguous`), plus `no_provider` (aucun pro vérifié éligible à la création) et `no_quote` (expirée sans devis).
- **Photos et note vocale : reportées.** Le stockage d'objets n'est pas branché à Django. Point d'extension : un futur `RequestAttachment` (FK demande, clé d'objet, type), sans toucher au contrat de création.
- **Point d'entrée IA1** : `RequestDraft` (dataclass : `trade_slug`, `service_slug`, zone, `landmark`, `description`, `urgent`, `preferred_*`). L'IA1 produira un brouillon à partir de `active_trades()`, le client le validera, puis il passera par le même `create_request`.

### Diffusion et devis

- **Éligibilité** (`requests.selectors.requests_for_provider`) : demande `open` ou `quoted` non expirée, métier et zone dans la fiche, pro `verified`, moins de 3 devis actifs, pas de devis actif de ce pro, client ≠ gérant, pro non exclu (il s'est désisté de cette demande). Une demande d'un compte de revue n'est visible que des pros `is_demo`.
- **Ordre et équité** : diffusion simultanée à tous les pros éligibles, triés par urgence puis par ancienneté. Les 3 places vont aux premiers devis. Un pro a au plus 10 devis `submitted` à la fois (`409 pro_quote_limit`). Pas de matching (IA4, V2).
- **Vue du pro avant `scheduled`** : métier, service, nom de la zone, description (numéros masqués), urgence, moment souhaité, places restantes. Jamais le nom, le numéro, le repère ou la position du client.
- **Notifications** : point d'extension `notifications.events.notify(kind, recipients, ref)`, appelé après commit. En `local`/`test`, l'adaptateur `log` écrit le type et les `public_id`, sans donnée personnelle. Push et SMS : étape 6. Types : `request.new`, `quote.received`, `booking.to_confirm`, `booking.scheduled`, `booking.cancelled`.

`Quote` : `request` · `provider` · `status` (`submitted`, `held`, `accepted`, `declined`, `withdrawn`, `expired`) · `kind` (`fixed`, `visit`) · `total_xof` (`PositiveBigIntegerField`, > 0, ≤ `QUOTE_MAX_XOF` = 5 000 000) · `visit_deductible` (booléen, `visit` seulement) · `message` (500) · `slot_start`/`slot_end` (UTC, issus d'un jour et d'une plage `Africa/Dakar`, dans le futur) · `valid_until` (48 h par défaut, 12 h si la demande est urgente, borné par `expires_at`) · `idempotency_key`. `QuoteLine` : `kind` (`labor`, `parts`, `travel`, `other`), `label` (60, facultatif), `amount_xof` (> 0), 1 à 8 lignes. Le total est la somme des lignes (vérifiée en service et testée).

- **`fixed`** (« Prix ferme ») : au moins une ligne `labor` ou un message de 20 caractères au moins (`quote_details_required`), contre les devis bâclés.
- **`visit`** (« Visite seulement : le prix des travaux sera donné sur place ») : `total_xof` ≤ `QUOTE_VISIT_MAX_XOF` (15 000 par défaut) ; mention « déduit si vous faites les travaux » si `visit_deductible`. **En V1, l'accord sur le prix des travaux se fait hors devis, entre le client et le pro, tant que l'avenant (étape 4) n'existe pas.** Le web l'écrit sans détour.
- Un seul devis actif par pro et par demande (`UniqueConstraint` partielle). Pour modifier son devis, le pro le retire puis en envoie un nouveau, si une place reste libre.
- 3 devis actifs au plus, comptés sous `select_for_update` de la demande. Le 4e pro reçoit `409 quotes_full`, et la demande sort de sa liste. Elle y revient si une place se libère.
- Retrait (`submitted` seulement), expiration à `valid_until`. Un numéro masqué dans `message` incrémente `masked_numbers_count`.

### `bookings`

`Booking` : `request` (FK, une seule active, ADR 0010) · `quote` (OneToOne) · `client` · `provider` · `status` · `amount_xof` (copie du devis, informatif) · `slot_start`/`slot_end` · `confirm_deadline` · `cancelled_by` (`client`, `pro`, `system`) · `cancel_reason`. `BookingEvent` (immuable) : `booking`, `from_status`, `to_status`, `actor` (nul pour `system`), `actor_kind`, `reason`, `note` (200), `metadata` (schéma fermé : `late`, `reliability_weight`), `created_at`.

Machine déclarée en entier (`accepted`, `scheduled`, `en_route`, `on_site`, `in_progress`, `completed`, `disputed`, `closed`, `cancelled`). `transition(booking, to, actor, actor_kind, reason, note="")` verrouille la ligne, vérifie le couple et l'acteur, écrit le statut et un `BookingEvent`, puis notifie après commit. Un couple déclaré mais non activé lève `transition_not_enabled`. Un test d'architecture interdit toute écriture de `status` hors de `bookings/services.py`.

| Transition active       | Acteur                    | Effets                                                                                                                                        |
| ----------------------- | ------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------- |
| création → `accepted`   | client (accepte un devis) | `create_from_quote` : demande `booked`, autres devis `held`, `confirm_deadline` calculée (ci-dessous)                                         |
| `accepted → scheduled`  | pro (confirme)            | devis `held` → `declined` ; contact et adresse divulgués au pro, contact du pro au client                                                     |
| `accepted → cancelled`  | client, pro, `system`     | `system` : `pro_unconfirmed` (tâche) ou `provider_suspended`. Par le pro ou le système : devis `held` encore valides → `submitted`, pro exclu |
| `scheduled → cancelled` | client, pro, `system`     | `late = true` à moins de 2 h de `slot_start`. Par le pro : demande rouverte en `open` (nouvelle échéance), pro exclu                          |

- **Délai de confirmation** : `BOOKING_CONFIRM_TTL` = 4 h, `BOOKING_CONFIRM_TTL_URGENT` = 1 h. Le délai ne court pas entre 21 h et 7 h, heure de Dakar (`BOOKING_CONFIRM_QUIET_HOURS`), et il est borné par `slot_start`. Fonction pure `confirm_deadline()`, testée sur les cas limites (acceptation à 20 h 30, à 23 h, urgente la nuit).
- **Motifs** (codes en dur : ils pilotent la fiabilité, contrairement aux libellés de données de l'ADR 0009) : client `changed_mind`, `found_other`, `price`, `unavailable`, `other` ; pro `unavailable`, `too_far`, `job_mismatch`, `other` ; `system` `pro_unconfirmed`, `provider_suspended`. `other` exige une note (numéros refusés : `note_invalid`).
- **Fiabilité** (V1 : trace seulement, le score viendra plus tard) : `reliability_weight` est calculé par une fonction pure et testée.
  - Côté pro : aucun motif ne compte avant `scheduled`, `pro_unconfirmed` compris. Après `scheduled`, tout désistement compte 1, et 2 s'il est `late`.
  - Côté client : jamais rien contre le pro, `price` compris. Une annulation tardive du client est tracée (`late`), sans pénalité.
  - Le client reçoit un message neutre : « Le pro ne peut plus venir, voici vos autres devis ».
- **Joindre le pro en V1** : à `scheduled`, le client voit le numéro du pro et le pro celui du client (lien d'appel et WhatsApp). Avant, aucun numéro. La messagerie masquée (`messaging`) viendra plus tard.

### Tâches Celery (beat, toutes les 5 min, idempotentes)

`requests.tasks.expire_due` (demandes et devis échus) et `bookings.tasks.cancel_unconfirmed`. Les sélecteurs filtrent aussi sur l'heure courante : un retard de beat ne montre jamais un objet échu.

### Endpoints

Tags `requests`, `pro`, `bookings`. Listes en curseur. Identifiants en `public_id`. Un objet d'un autre utilisateur répond `404`. Création : `Idempotency-Key` obligatoire. Même clé et même corps → même réponse ; même clé et autre corps → `409 idempotency_key_reused`. Une clé n'est retenue qu'après une création réussie : après un `422` (dont `zone_ambiguous`), le client la rejoue avec le `zone_slug` choisi.

| Méthode | Chemin                                                     | Permission                     | Notes                                                                                |
| ------- | ---------------------------------------------------------- | ------------------------------ | ------------------------------------------------------------------------------------ |
| POST    | `/api/requests/`                                           | `RequiresCompleteProfile`      | `201` détail ; `422` motifs ci-dessus ; `409 request_limit_reached`                  |
| GET     | `/api/requests/`, `/api/requests/{id}/`                    | `IsClient`                     | Détail : devis triés par `slot_start` (jamais par prix) + réservation active         |
| POST    | `/api/requests/{id}/cancel/`                               | `IsClient`                     | `{reason, note?}` ; `409 request_closed` si `booked`                                 |
| POST    | `/api/quotes/{id}/accept/`                                 | `RequiresCompleteProfile`      | `201` réservation ; rejouer → `200` même réservation ; `409 quote_not_available`     |
| GET     | `/api/bookings/`, `/api/bookings/{id}/`                    | `IsClient` (côté client)       | `confirm_deadline` ; `contact` (nom commercial, numéro du pro) à `scheduled`         |
| POST    | `/api/bookings/{id}/cancel/`                               | `IsClient`                     | `{reason, note?}`                                                                    |
| GET     | `/api/pro/me/`                                             | `HasOwnerRole`                 | Fiche : statut, métiers, zones                                                       |
| GET     | `/api/pro/requests/`, `/api/pro/requests/{id}/`            | `IsVerifiedPro`                | Vue masquée ; ordre urgence puis ancienneté                                          |
| POST    | `/api/pro/requests/{id}/quotes/`                           | `IsVerifiedPro`                | `201` ; `409 quotes_full`, `quote_already_sent`, `pro_quote_limit`, `request_closed` |
| GET     | `/api/pro/quotes/` · POST `/api/pro/quotes/{id}/withdraw/` | `IsVerifiedPro` + `IsProOwner` |                                                                                      |
| GET     | `/api/pro/bookings/`, `/api/pro/bookings/{id}/`            | `HasOwnerRole` + `IsProOwner`  | À `scheduled` : nom et numéro du client, repère, position                            |
| POST    | `/api/pro/bookings/{id}/confirm/`, `/cancel/`              | `IsVerifiedPro` + `IsProOwner` | `409 transition_not_allowed`                                                         |

Codes d'erreur i18n ajoutés : `request_limit_reached`, `zone_ambiguous`, `trade_not_in_zone`, `out_of_area`, `service_not_in_trade`, `landmark_or_location_required`, `description_required`, `request_closed`, `quotes_full`, `quote_already_sent`, `pro_quote_limit`, `quote_not_available`, `quote_total_invalid`, `quote_details_required`, `slot_invalid`, `provider_not_verified`, `own_request`, `transition_not_allowed`, `transition_not_enabled`, `note_invalid`, `idempotency_key_reused`, `deletion_blocked_active_booking`.

### Données personnelles

- **Anonymiseurs** : `requests` vide `landmark`, `location`, `description` et `zone_text`, annule les demandes ouvertes et décline leurs devis. `bookings` vide les notes. `providers` remplace le nom commercial et suspend la fiche.
- **Blocage de la suppression** : un compte avec une réservation `accepted` ou `scheduled` (client ou pro) ne peut pas être supprimé (`register_deletion_blocker`). `create_from_quote` crée la réservation sous le verrou des deux comptes.
- **Rétention** : `landmark` et `location` sont vidés 30 jours après une demande expirée ou annulée sans réservation (purge quotidienne). Pour les réservations, la durée sera fixée à l'étape 4 (garantie, litiges).

## Points de sécurité

- Toute liste passe par un sélecteur qui prend `user` ou `provider`. Chaque endpoint a ses tests autorisé, refusé (objet d'un autre : 404) et invalide.
- Repère, position, nom et numéro du client : jamais dans une réponse pro avant `scheduled`, ni après une annulation (test par statut).
- `landmark`, `location`, `description`, `note` et `message` n'apparaissent jamais dans un log, un audit, Sentry ou une URL. Le point GPS n'est jamais journalisé, même arrondi. Le compteur de masquages ne garde aucun texte.
- `IsProOwner` est vérifié sur l'objet, et les sélecteurs le doublent. Un pro suspendu ne devise plus et ne confirme plus.
- Concurrence : `select_for_update` sur la demande (devis, acceptation) et sur la réservation (`transition`). Deux acceptations simultanées donnent une seule réservation (test en transaction réelle).
- `is_demo`, `seed_demo_pros` et `demo_pro` sont refusés hors `local`/`test` (contrôle au démarrage et dans la commande).
- Revue `security-reviewer` sur les tâches marquées [sécu].

## IA (si applicable)

Aucune IA dans cette spec. Le point d'entrée est `RequestDraft` + `create_request`, décrits plus haut. L'IA1 (spec suivante) recevra `active_trades()`. Un métier inconnu qu'elle détecte sera signalé en `trade_not_found`, avec le terme normalisé.

## Hors périmètre

- `en_route` → `closed`, code de fin, photos, avis, avenants (étape 4) ; techniciens et invitations (étape 4) ; argent et commission (étape 5) ; calcul d'un score de fiabilité.
- Photos et note vocale de la demande ; messagerie et masquage dans le chat ; Channels (temps réel) ; push et SMS réels (étape 6).
- Changement de créneau, re-réservation de « Mon plombier », frais de déplacement calculés, matching (IA4), demande pour un proche (diaspora, V3).
- « Prévenez-moi quand ce métier ouvre » dans mon quartier (Q5), pour plus tard.
- Inscription pro en libre-service, console Ops et console Pro, app Pro (étape 6).

## Critères d'acceptation

- [ ] En local, de bout en bout : Zay crée une demande sur le web, `demo_pro autoquote` produit 3 devis, il en accepte un, `demo_pro confirm` passe la réservation à `scheduled`, et le web affiche le créneau et le numéro du pro.
- [ ] Un 4e devis reçoit `409 quotes_full`. Un retrait libère une place, et la demande revient dans les listes.
- [ ] `zone_unknown` crée une demande `needs_zone`, sans échéance tant que l'Ops ne l'a pas rattachée. `zone_ambiguous` ne crée rien, et le rejeu avec la même clé et un `zone_slug` réussit. `trade_not_in_zone` et `no_quote` écrivent un `UnservedDemand` sans identifiant d'utilisateur.
- [ ] Chaque couple de la machine est testé : actif, déclaré non activé (`transition_not_enabled`), interdit. Chaque transition écrit un `BookingEvent`. Le test d'architecture passe.
- [ ] `confirm_deadline()` respecte le gel de 21 h à 7 h (Dakar) et `slot_start`. Une non-confirmation annule la réservation (`pro_unconfirmed`, poids 0), remet les devis `held` en `submitted` et exclut le pro.
- [ ] Un devis `visit` au-delà du plafond est refusé ; un devis `fixed` sans ligne `labor` ni message de 20 caractères aussi.
- [ ] Une `Idempotency-Key` rejouée ne crée ni deuxième demande, ni deuxième devis, ni deuxième réservation.
- [ ] Aucun numéro, repère ou position du client dans les réponses pro avant `scheduled`. Les numéros sont masqués dans la description et le message, et le compteur du pro augmente.
- [ ] Anonymiseurs et blocage de la suppression testés. `make openapi` à jour, client TS régénéré, clés i18n `fr` présentes.

## Tâches par couche

Chacune livrable et testable seule, dans l'ordre.

- api :
  1. [sécu] **`providers`** : `Provider`, `onboard_provider` + commande, `set_status` + actions d'admin et groupe `Validation pros`, schéma d'audit, `IsVerifiedPro`, `IsProOwner` objet, contrôle `is_demo`, anonymiseur, fabriques, tests.
     **Fait :** app `providers` (`Provider`, `onboard_provider`, `set_status`, commande `onboard_provider` dont `--operator` est le `public_id` d'un Admin actif), actions d'admin « Vérifier » et « Suspendre » (groupe `Validation pros`, migration 0002, permission `providers.verify_provider`), `IsVerifiedPro` et `IsProOwner` dans `accounts/permissions.py`, contrôle `providers.E001` (pros de démo hors local/test). Écart minimal : la suspension déclenche ses effets par un registre `register_suspension_handler` (requests et bookings s'y inscrivent dans leur `ready()`), pour que `providers` n'importe jamais leurs services.
  2. **`analytics` minimal** : `UnservedDemand`, `record_unserved()`, admin en lecture seule, tests.
     **Fait :** app `analytics` (`UnservedDemand`, `record_unserved`, admin en lecture seule, lisible du groupe `Saisie catalogue`). Écart minimal : un slug absent est une chaîne vide en base (et non `null`, règle `DJ001`) ; l'événement de la spec 002 le notait `null`.
  3. [sécu] **`requests` : demande** : `ServiceRequest`, `RequestDraft`, `create_request` (résolution par `availability`, champs obligatoires, limites, idempotence), table de transitions, annulation, action d'admin « Rattacher », expiration, purge, anonymiseur, `demande` ajouté à `RESERVED_TRADE_SLUGS`, tests.
     **Fait :** app `requests` (`ServiceRequest`, `RequestDraft`, `create_request`, table de transitions testée couple par couple, `cancel_request`, `attach_zone`, `expire_due`, `purge_locations`, anonymiseur, action d'admin « Rattacher à une zone » avec page intermédiaire, groupe `Saisie catalogue` étendu par la migration 0002, `demande` réservé). Écarts minimaux : `ServiceRequest.dispatch_rank` (clé unique d'ordre urgence puis ancienneté, pour que la pagination par curseur du pro reste exacte) ; `ServiceRequest.excluded_providers` (M2M des pros désistés) ; la contrainte « repère ou position » ne vaut que tant que la demande vit (elle est vidée ensuite, RGPD) ; une relecture d'une création idempotente renvoie `created=False` (l'API répondra `200`, `201` à la première) ; codes 422 ajoutés : `zone_required`, `location_invalid`, `text_too_long`, `reason_invalid`, `request_rate_limited` (429).
  4. **`requests` : devis** : `Quote`, `QuoteLine`, éligibilité, `submit_quote` (3 places, verrou, plafond par pro, règles `fixed` et `visit`), retrait, expiration, masquage et compteur, tests de concurrence.
     **Fait :** `Quote`, `QuoteLine`, `requests/quotes.py` (`submit_quote`, `withdraw_quote`, `expire_quotes`, effets d'une clôture ou d'une réservation sur les devis), sélecteurs de diffusion (`requests_for_provider`, `request_for_provider`, `quotes_for_client_request`…), `common.pii.mask_numbers` (masque et compte), tâche `expire_due` étendue aux devis, suspension d'un pro : ses devis `submitted` sont retirés. Test de concurrence en transaction réelle (5 pros, 3 places). Écart minimal : le total (`total_xof`) est une entrée vérifiée contre la somme des lignes, pas un calcul silencieux ; erreurs de structure (`quote_total_invalid`) groupées sous ce code.
  5. [sécu] **`bookings`** : `Booking`, `BookingEvent`, machine déclarée, `transition()`, `create_from_quote`, `confirm_deadline()`, `reliability_weight`, confirmation, annulations, `cancel_unconfirmed`, blocage de la suppression, test d'architecture, tests exhaustifs des transitions.
     **Fait :** app `bookings` (`Booking`, `BookingEvent` immuable jusqu'en base par trigger, machine déclarée en entier dans `machine.py`, `transition()`, `create_from_quote`, `confirm_deadline()`, `reliability_weight`, `confirm_booking`, `cancel_booking`, `cancel_unconfirmed` et sa tâche, annulation à la suspension d'un pro, blocage de la suppression, anonymiseur des notes) ; tests exhaustifs des couples (actif, déclaré non activé, interdit), des cas limites du gel nocturne, deux acceptations simultanées en transaction réelle, test d'architecture (aucune écriture de `status` hors `bookings/services.py`, idem pour la demande). Écarts minimaux : `transition()` prend `booking` en positionnel et le reste nommé ; `machine.DISCLOSED_STATUSES` fixe les statuts où le contact est divulgué ; une confirmation arrivée après l'échéance annule la réservation (`pro_unconfirmed`) et répond `409 transition_not_allowed` ; une réservation `accepted` échue n'est plus montrée même si la tâche a du retard ; `purge_locations` épargne les demandes qui ont eu une réservation.
  6. **`notifications`** : `notify()` et l'adaptateur `log`, branchés sur les 5 types, tests (aucune donnée personnelle dans la ligne écrite).
     **Fait :** `notifications/events.py` (`notify(kind, recipients, ref)` planifié après commit, adaptateurs `log` et `none`, réglage `NOTIFICATIONS_ADAPTER`), branché sur `request.new` (création ouverte et rattachement à une zone), `quote.received`, `booking.to_confirm`, `booking.scheduled`, `booking.cancelled` ; une panne d'adaptateur n'annule jamais l'action ; test que la ligne écrite ne contient que le type et des `public_id`.
  7. [sécu] **API** : vues et sérialiseurs client et pro (vues masquées distinctes), pagination, idempotence, codes i18n, tests autorisé, refusé et invalide, `make openapi`.
     **Fait :** vues et sérialiseurs client et pro (la vue du pro n'a aucun champ du client), pagination par curseur (liste du pro : clé `dispatch_rank`), `Idempotency-Key` (`common/api/idempotency.py`), 18 opérations OpenAPI (tags `requests`, `bookings`, `pro`), `ENUM_NAME_OVERRIDES` pour des noms d'énumération stables, schéma et client TS régénérés (`make openapi`), tests statut par statut de la divulgation. Écarts minimaux : les rejeux d'une création répondent `200` (premier appel `201`) ; l'accepte d'un devis n'exige pas d'`Idempotency-Key` (idempotent par nature, `200` au rejeu) ; une demande que le pro ne peut pas voir (autre métier, autre zone, close, la sienne, désistement) répond `404 not_found` plutôt que `own_request` ou `request_closed` (les services gardent ces codes) ; `request.new` n'est pas diffusé avant le rattachement d'une zone.
  8. **Démo locale** : `seed_demo_pros` (3 pros vérifiés `is_demo`, métiers et zones du seed 002, idempotent) et `demo_pro` (`list`, `quote`, `autoquote`, `withdraw`, `confirm`, `cancel`), tous deux via les services, refusés hors `local`. Cible `make demo`.
     **Fait :** `seed_demo_pros` (3 pros `is_demo` vérifiés, tout le catalogue et toutes les zones, idempotent), `demo_pro` (`list`, `quote` avec `--visit`, `autoquote`, `withdraw`, `confirm`, `cancel`), cible `make demo` ; refusés hors `DJANGO_ENV=local`. `providers.services.set_status` accepte `actor=None` (événement système). Parcours vérifié en local : demande créée par l'API, 3 devis par `autoquote`, acceptation, `demo_pro confirm`, réservation `scheduled` avec le numéro du pro.
  9. **Documentation** : ARCHITECTURE.md (deux diagrammes, ADR 0010), `apps/api/CLAUDE.md` (permissions), `chantier-prod.md` à jour.
     **Fait :** ARCHITECTURE.md (deux diagrammes, règles de la demande et de la réservation, tableau des domaines, ADR 0010), `apps/api/CLAUDE.md` (permissions `IsVerifiedPro`, `IsProOwner`, conventions de la spec 003), `chantier-prod.md` (6 besoins prod relevés).
- web :
  1. **Nouvelle demande** (`/demande`, session exigée), via une Server Action et le BFF :
     - métiers et zones du catalogue, recherche hors ligne `@jeflink/api-client/search`, « Autre quartier » ;
     - obligatoires : métier, quartier, et repère ou position. La description est facultative si un service est choisi ;
     - exemples de repère (« près de la boutique, portail bleu, 2e étage ») et la phrase « Le repère exact sera communiqué au pro après confirmation » ;
     - brouillon sauvegardé localement (sans la position) et restitué à la réouverture, effacé après la création ;
     - `Idempotency-Key` gardée pour les nouvelles tentatives, rejouée avec le `zone_slug` choisi après `zone_ambiguous` ;
     - position envoyée seulement dans le `POST` ; `trade_not_in_zone` avec CTA WhatsApp ; `needs_zone` affiche « Nous vérifions votre quartier ».
  2. **Mes demandes** (`/compte/demandes`, `/compte/demandes/[id]`) :
     - une carte par devis : total en XOF avec séparateur d'espace, « Prix ferme » ou « Visite seulement », créneau en langage courant (« Demain matin »), nom commercial et « Pro vérifié », détail des lignes replié ;
     - tri par créneau le plus proche, jamais par prix ; mention « Les coordonnées sont partagées après confirmation » ;
     - acceptation avec confirmation, puis attente (« Le pro a jusqu'à HH:MM… »), créneau, contact du pro, mention de paiement, annulation avec motif.
  3. Clés i18n courtes `fr` (`wo` vide retombe sur `fr`), revue `design-guardian` (jamais d'icône seule).
- console : rien. client / pro : rien (étape 6). Le client TS régénéré suffit.

## Questions à trancher (Zay)

✅ Q1 à Q7 acceptées par Zay le 2026-10-03, avec les ajustements terrain. Zay confirme aussi que tout désistement du pro après `scheduled` compte en fiabilité, quel que soit le motif.

1. **Q1 — Divulgation à `scheduled`** (repère, position, deux numéros), pas à l'acceptation. _Terrain : accepté._
2. **Q2 — Confirmation par le pro** sous 4 h (1 h si urgente), délai gelé de 21 h à 7 h (Dakar), sans pénalité en V1, autres devis rendus au client sinon. _Terrain : accepté avec ces ajustements._
3. **Q3 — Durées et limites** : demande 72 h après `open` (24 h si urgente), devis valable 48 h (12 h si urgente), 3 demandes ouvertes par client, 10 devis en attente par pro. _Terrain : accepté._
4. **Q4 — Devis « Visite seulement »** dès la V1, plafonné à 15 000 XOF, avec « déduit si vous faites les travaux », et l'accord sur les travaux hors devis jusqu'à l'avenant. _Terrain : accepté avec ces ajustements._
5. **Q5 — Métier non ouvert dans le quartier** : refus avec un message clair et un lien WhatsApp, signal enregistré ; « Prévenez-moi » plus tard. _Terrain : accepté._
6. **Q6 — Côté pro en local** : API, `seed_demo_pros`, `demo_pro` et admin Django, sans espace pro web. _Terrain : accepté._
7. **Q7 — Places restantes visibles du pro** (« 1 place sur 3 », sans les montants des autres). _Terrain : accepté._
