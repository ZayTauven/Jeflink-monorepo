# Jeflink — Architecture

## Vue d'ensemble

```mermaid
flowchart LR
  subgraph Clients
    W[web · Next] --- C[console · Next]
    MC[app client · Expo] --- MP[app Pro · Expo]
    WA[WhatsApp · V2]
  end
  subgraph Backend
    API[Django + DRF]
    WS[Channels · temps réel]
    WK[Celery workers]
    AI[domaine ai]
  end
  PG[(PostgreSQL + PostGIS)]
  R[(Redis)]
  S3[(Stockage objets)]
  W & C & MC & MP --> API
  MC & MP --> WS
  WA --> API
  API --> PG & R & S3
  WK --> PG & S3
  API --> AI
  AI --> LLM[Claude API]
  AI --> ASR[Reconnaissance vocale · adaptateur]
  API --> PAY[PaymentGateway → WiiPay · V2]
  WK --> NOTIF[Push · SMS · WhatsApp]
```

## Domaines backend

| Domaine         | Responsabilité                                                                                                                                                                              |
| --------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `accounts`      | Comptes par téléphone, OTP SMS, sessions d'appareil (JWT + refresh rotatif), rôles et invitations, second facteur Ops, changement de numéro, suppression et anonymisation, purge (spec 001) |
| `zones`         | Quartiers (centre + rayon, contour optionnel), villes, disponibilité des métiers par zone                                                                                                   |
| `catalog`       | Métiers, services, fourchettes de prix de référence. Métiers = lignes en base (slug stable, libellés `fr`/`wo`, actif oui/non), jamais un `enum` ou des `choices` dans le code              |
| `providers`     | Fiche pro (statut `pending`, `verified`, `suspended`, métiers, zones), création et vérification par l'Ops (spec 003) ; équipes, disponibilités, badges, Passeport Pro plus tard                |
| `requests`      | Demande (cycle `needs_zone` à `expired`), devis (3 au plus, prix ferme ou visite), diffusion aux pros éligibles ; photos et voix plus tard (spec 003, ADR 0010)                             |
| `bookings`      | Réservation née à `accepted`, machine à états déclarée en entier, `BookingEvent`, confirmation du pro ; avenants, code de fin, preuves à l'étape 4 (spec 003, ADR 0010)                    |
| `payments`      | Interface `PaymentGateway`, intentions, webhooks                                                                                                                                            |
| `wallet`        | Grand livre en partie double, soldes dérivés, versements                                                                                                                                    |
| `reviews`       | Avis (note, puces, commentaire facultatif), publication à la clôture, moyenne, modération                                                                                                                                                              |
| `messaging`     | Conversations, pièces jointes, masquage des numéros avant réservation                                                                                                                       |
| `notifications` | `notify(kind, recipients, ref)` après commit (adaptateur `log` en local/test) ; push, SMS (`SmsGateway`, adaptateur `fake` en local/test seulement), WhatsApp, préférences, replis            |
| `trust`         | KYC, litiges, garantie, signalements, `AuditEvent`                                                                                                                                          |
| `promotions`    | Codes promo, parrainage                                                                                                                                                                     |
| `analytics`     | `UnservedDemand` (demandes non servies, sans identifiant d'utilisateur) ; autres événements produit plus tard                                                                              |
| `ai`            | Fournisseurs, prompts versionnés, schémas, évals, journal de coûts                                                                                                                          |

## Demande, devis et réservation : deux cycles de vie

Référence : spec `docs/specs/003-requests-quotes-booking.md`, ADR 0010. Le client décrit son besoin (la **demande**), au plus 3 pros vérifiés envoient un **devis**, le client en accepte un : la **réservation** naît alors à `accepted`. Avant ce choix, il n'y a ni pro, ni montant, ni créneau : la demande porte son propre cycle, et seule `requests.services` en change le statut (table de transitions testée couple par couple).

### Cycle de vie d'une demande (`requests.ServiceRequest`)

```mermaid
stateDiagram-v2
  [*] --> needs_zone : quartier inconnu
  [*] --> open : demande créée
  needs_zone --> open : l'Ops rattache une zone
  open --> quoted : 1er devis reçu
  quoted --> open : plus aucun devis actif
  quoted --> booked : le client accepte un devis
  booked --> quoted : le pro se désiste, d'autres devis restent
  booked --> open : le pro se désiste, aucun autre devis
  booked --> cancelled : le client annule la réservation
  needs_zone --> cancelled : le client annule
  open --> cancelled : le client annule
  quoted --> cancelled : le client annule
  open --> expired : échéance (72 h, 24 h si urgente)
  quoted --> expired : échéance
```

Les durées et limites sont des réglages (`settings`), jamais en dur : expiration de la demande, validité d'un devis, 3 devis actifs par demande, 10 devis en attente par pro, 3 demandes non closes et 10 créations par jour et par client, délai de confirmation du pro. Le temps passé en `needs_zone` ne compte pas dans l'échéance.

### Machine à états d'une réservation (`bookings.Booking`)

```mermaid
stateDiagram-v2
  [*] --> accepted : le client accepte un devis
  accepted --> scheduled : le pro confirme (code de fin généré)
  accepted --> cancelled : client, pro, ou délai dépassé
  scheduled --> cancelled : client, pro, ou pro suspendu
  scheduled --> en_route : le pro part (SMS du code)
  en_route --> cancelled : client, pro, système
  en_route --> on_site : le pro arrive
  on_site --> cancelled : pro (client_absent, job_mismatch), système
  on_site --> in_progress : photos « avant » ou photos_pending
  in_progress --> in_progress : avenant accepté par le client
  in_progress --> completed : code de fin, ou sans code avec motif
  completed --> closed : fin de la fenêtre de contestation (système)
  completed --> disputed : le client ouvre un litige
  disputed --> closed : décision de l'Ops
```

Spec 004 : **tous les couples sont activés**. Un couple interdit lève `transition_not_allowed` ; le mécanisme `transition_not_enabled` reste pour un futur couple déclaré mais inactif. `scheduled`, `en_route` ou `on_site` peuvent finir en `cancelled` ; le client ne peut pas annuler un pro déjà sur place.

Règles :

- Chaque transition passe par `bookings.services.transition()`, qui verrouille la ligne, vérifie le couple et l'acteur (`client`, `pro`, `system`, `ops`), écrit le statut et un `BookingEvent` immuable. Un test d'architecture interdit toute écriture de `status` hors de `bookings/services.py`.
- **Confirmation du pro** : 4 h (1 h si urgente), délai gelé de 21 h à 7 h (heure de `Africa/Dakar`) et borné par le début du créneau (`machine.confirm_deadline`, fonction pure). Sans confirmation, la tâche `bookings.tasks.cancel_unconfirmed` annule (`pro_unconfirmed`, poids de fiabilité 0), rend les autres devis au client et exclut le pro de la demande.
- **Fiabilité (trace seulement)** : un désistement du pro après `scheduled` pèse 1, et 2 s'il a lieu à moins de 2 h du créneau (`late`) ; rien avant `scheduled`. Le client n'est jamais pénalisé (une annulation tardive est tracée).
- **Divulgation** : le repère, la position et le numéro du client (vers le pro), le numéro du pro (vers le client) ne sont renvoyés qu'à partir de `scheduled` (`machine.DISCLOSED_STATUSES`), jamais après une annulation. Avant, les numéros saisis dans une description ou un message de devis sont masqués à l'affichage (`common.pii.mask_numbers`) ; ce masquage n'est pas étanche et un compteur par pro (`Provider.masked_numbers_count`) aide l'Ops à repérer les abus.
- **Ordre des verrous** : comptes (par id), fiche pro, demande, réservation. Deux acceptations simultanées donnent une seule réservation.
- **Argent** : aucun. Les montants de devis sont des entiers XOF informatifs ; aucun `LedgerEntry` (étape 5). Mention fixe sur la réservation : à régler au pro.
- **Notifications** : `notifications.events.notify(kind, recipients, ref)`, appelé après commit, ne transporte que des `public_id` (`request.new`, `quote.received`, `booking.to_confirm`, `booking.scheduled`, `booking.cancelled`, puis, spec 004 : `completion_code.sms`, `amendment.proposed`, `booking.dispute_reminder` (SMS), `booking.progress`, `amendment.decided`, `booking.completed`, `booking.no_show_check`, `no_show.contested`, `booking.disputed`, `dispute.decided`, `booking.closed`). Le futur adaptateur SMS rend le gabarit (code, prix) côté serveur à partir de la référence. Push et SMS : étape 6.

### Déroulé, fin de mission, litige et avis (spec 004)

- **Code de fin** : 4 chiffres tirés à `scheduled`, chiffrés (MultiFernet, `DATA_ENCRYPTION_KEYS`), comparés en temps constant, effacés à `completed` ou `cancelled`. Visible du client seul ; jamais dans une réponse au pro, un log ni un audit. Cinq codes faux le verrouillent, trois régénérations, un SMS automatique au départ du pro et deux sur demande. Repli `no_code` (`client_absent`, `client_no_phone`, `code_locked`, `client_refuses` avec photo « après » obligatoire) : fenêtre de contestation de 72 h au lieu de 48 h.
- **Photos** (`BookingPhoto`, ADR 0011) : envoi multipart par le gérant, réencodé en WebP sans EXIF ni GPS dans la requête, miniature par tâche Celery, URL signées de 10 min, signalement par le client (masquée pour les deux, gardée pour l'Ops en cas de litige), purge 12 mois après la clôture. Repère et position de la demande vidés 90 jours après la clôture.
- **Avenant** (`Amendment`) : le pro propose le nouveau prix complet (3 au plus, un seul en attente) ; seul le client, depuis sa session, le fait changer : `accept_amendment` est le seul endroit où `Booking.amount_xof` change après la création (test d'architecture). Aucun mouvement d'argent.
- **No-show** (`NoShowReport`) : déclaré par le client après `slot_end` + 60 min, la réservation est annulée et la demande rouverte tout de suite ; le poids de fiabilité 3 n'est journalisé qu'après 24 h sans contestation du pro, ou sur décision de l'Ops (groupe `Médiation`).
- **Clôture** : `close_due` (beat, 5 min) clôt à `dispute_deadline` ; `bookings.services.register_close_handler(fn)` appelle `fn(booking, reason)` dans la transaction de toute arrivée à `closed`. `reviews` y publie les avis ; `wallet` s'y inscrira (étape 5).
- **Litige** (`trust.Dispute`) : `bookings.services` appelle `trust.services`, jamais l'inverse. L'Ops tranche dans l'admin (`resolve_dispute`, aucun remboursement en V1) ; `for_client` journalise un poids de 2 et rouvre l'avis 7 jours.
- **Avis** (`reviews.Review`) : une note suffit, publié à la clôture, moyenne (`rating_for_providers`) à partir de 3 avis publiés, hors masqués, comptes de revue et pros de démo ; modération (`Modération avis`) sans suppression.

## Argent

- Grand livre en partie double (`wallet.LedgerEntry`) : chaque mouvement = au moins deux écritures équilibrées. Les soldes sont dérivés, jamais stockés comme source de vérité.
- Comptes types : `client_escrow`, `pro_available`, `pro_pending`, `pro_commission_due`, `platform_revenue`.
- Paiement cash : écriture `pro_commission_due` à la clôture. Paiement en ligne (V2) : fonds en `pro_pending` jusqu'à `closed`, commission prélevée, reste en `pro_available`.
- `PaymentGateway` : `create_intent`, `confirm`, `refund`, `payout`, `verify_webhook`. Adaptateurs : `cash`, `manual_mobile_money` (V1), `wiipay` (V2), `fake` (tests).

## Couche IA (`apps/api/jeflink/ai`)

```
ai/
  providers/     anthropic.py, fake.py          # client LLM derrière une interface
  speech/        base.py, <adaptateur>.py       # reconnaissance vocale, à benchmarker
  prompts/       structure_request/v1.md ...    # prompts versionnés, jamais en dur
  schemas.py     # sorties Pydantic validées
  services.py    # structure_request, price_range, draft_quote, summarize_dispute...
  evals/         # jeux de cas réels anonymisés + scripts de score
  models.py      # AIRun : capacité, version de prompt, latence, coût, résultat, validé ou non
```

- Modèles configurés par variables d'environnement (`AI_MODEL_DEFAULT`, `AI_MODEL_FAST`), jamais en dur dans le code.
- Chaque capacité a : un schéma de sortie, un seuil de confiance, un repli sans IA, un jeu d'évaluation, un feature flag.
- Données envoyées au modèle minimisées (pas de numéro, pas de nom complet, pas de pièce d'identité).

## Temps réel et notifications

- Channels + Redis : chat, statut de réservation, position « en route ».
- Notification critique : push → SMS si non lu après N minutes → WhatsApp (V2).

## Auth

Référence : spec `docs/specs/001-accounts.md`, ADR 0007 (sessions, BFF) et 0008 (SMS).

- **Connexion par code SMS** (`otp/request`, `otp/verify`) : le téléphone est l'identifiant, le compte n'est créé qu'après le code. Réponses identiques que le compte existe ou non. Limites par numéro, appareil, IP, préfixe et plafond global ; jamais d'ouverture si Redis tombe.
- **Sessions** : une `DeviceSession` par appareil ; access JWT court (HS256, `kid` en rotation), refresh opaque tourné à chaque usage avec une grâce unique de 24 h ; réutilisation détectée → session révoquée. Aucun rôle dans le jeton : les rôles sont relus en base. Bearer seul côté API (ni session Django, ni CSRF, ni CORS).
- **Web et console** : BFF Next, jetons en cookies `HttpOnly` ; le navigateur n'en voit jamais.
- **Compte dormant** : plus de 60 j sans activité et nouvel appareil → session restreinte (numéro peut-être recyclé). « Repartir de zéro » ou levée par l'Ops.
- **Ops** : second facteur TOTP obligatoire sur la console (enrôlement par jeton hors bande), TOTP de moins de 5 min pour les actions `manage` (step-up). Permissions par groupe (`HasOpsPerm("ops.<domaine>.<action>", step_up=…)`), jamais par `is_superuser`. Quotas par Ops sur la recherche et la révélation des numéros.
- **Admin Django** : équipe technique seulement, hôte interne, second facteur TOTP et limite de débit. Lecture seule, sauf la saisie du catalogue et des zones (groupe `Saisie catalogue`, spec 002) : ajout et modification, jamais de suppression ni de changement de slug.

## Règles transverses posées par `accounts`

- **Audit** : toute action sensible écrit un `AuditEvent` via `trust.services.audit()`, avec un schéma de métadonnées déclaré (`register_audit_schema`) ; numéros seulement masqués ou en HMAC ; audit hors transaction (`durable=True`) sur un chemin d'erreur.
- **Suppression du compte** : anonymisation, la ligne reste. Chaque domaine qui stocke des données personnelles enregistre un anonymiseur (`register_anonymizer`) ; un domaine peut refuser la suppression (`register_deletion_blocker`) **à condition de créer ses objets bloquants sous le verrou du compte**.
- **Compte de revue des stores** (`User.is_review_account`) : ses données ne sont jamais diffusées aux vrais pros.
- **Rétention** : purge quotidienne (`accounts.tasks.purge_auth_data`), durées en réglages (`AUTH_RETENTION`).

## Environnements

`local` (docker-compose) · `staging` · `production`. Observabilité : Sentry (api + fronts + apps), logs JSON structurés sans données personnelles.
