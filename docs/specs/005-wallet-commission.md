# Spec 005 — Portefeuille Pro et commission sur le cash

Statut : api livrée le 2026-10-05 (tâches 1 à 11), revue `security-reviewer` à faire · validée par Zay le 2026-10-05 · ADR lié : 0012 (grand livre et règlements, proposé), précise l'ADR 0002 · Revue `terrain-reviewer` faite le 2026-10-05 (voir « Revue terrain et arbitrages »)

## Problème

Ibou termine une mission à 30 000 F et le client le paie en espèces ou par Wave. Jeflink ne voit pas cet argent. Sans commission, la V1 n'a aucun revenu ; sans trace, la commission devient une discussion au téléphone. PRODUCT.md (§5, « Commission sur cash ») le règle : la commission est inscrite comme dette dans le portefeuille du pro, réglée en mobile money, avec un seuil de dette paramétrable. C'est l'étape 5 de `chantier-prod.md`. Elle s'accroche à la clôture posée par la spec 004 (`register_close_handler`) et écrit les premiers mouvements du grand livre.

| Zone sensible        | Touchée ? | Détail                                                                                                                                                                        |
| -------------------- | --------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Argent               | **Oui**   | Premier grand livre (`wallet`), premières intentions de paiement (`payments`). Entiers XOF, partie double, écritures immuables, soldes dérivés. Aucun fonds de client détenu. |
| KYC                  | Non       | Aucun.                                                                                                                                                                        |
| Machine à états      | Non       | Aucun couple ajouté ni modifié. `wallet` s'inscrit au registre de clôture ; `transition()` ne change pas.                                                                     |
| Auth, permissions    | **Oui**   | Groupes d'admin `Rapprochement` et `Comptabilité`, second facteur TOTP redemandé pour chaque action d'argent. Un pro suspendu lit son portefeuille et peut payer sa dette.    |
| Données personnelles | Oui       | Référence de transaction mobile money et 4 derniers chiffres du numéro payeur : jamais dans un log, un audit ni une URL. Rétention fixée.                                     |

## Parcours

- **Pro (API ; en local, `demo_pro`).**
  - Il voit, avant de deviser, le taux de commission de ses métiers.
  - À chaque clôture, la commission de la mission s'ajoute à sa dette. Il lit un solde (« Vous devez 4 500 F à Jeflink »), l'historique mission par mission et la façon de payer (numéro marchand Jeflink par canal).
  - Il paie depuis son téléphone (Wave, Orange Money) ou, s'il n'a pas de compte, par un dépôt chez un agent Wave ou Orange Money vers le numéro marchand.
  - S'il a payé depuis son propre numéro, il n'a rien d'autre à faire : l'Ops voit le versement dans le relevé et le crédite. Sinon, ou pour aller plus vite, il déclare le règlement : canal, montant, référence de la transaction, heure. Le montant passe « en vérification ».
  - Si l'Ops ne trouve pas sa référence (faute de frappe), la déclaration lui revient « à corriger » : il corrige une fois, sans repartir de zéro.
  - Au-delà d'un premier seuil, il reçoit une alerte. Au-delà du second, il ne peut plus envoyer de nouveaux devis. Ses missions en cours et ses réservations déjà acceptées ne sont jamais touchées.
- **Ops (admin Django).**
  - `Rapprochement` : compare chaque déclaration au relevé du compte marchand, puis la confirme (avec le montant réellement reçu), la renvoie « à corriger » ou la rejette avec un motif. Crédite un versement vu dans le relevé et venu du numéro du pro, sans déclaration. Enregistre un règlement en espèces remis au bureau, avec un numéro de reçu.
  - `Comptabilité` : saisit les taux, gère les canaux de règlement, passe les avoirs, les corrections et les contre-passations, toujours avec un motif.
  - Chaque action d'argent exige un code TOTP saisi depuis moins de 5 minutes et écrit un audit.
- **Système.** Écrit la commission à la clôture, relance chaque semaine les pros endettés, signale à l'Ops les déclarations en attente depuis trop longtemps.
- **Client.** Rien ne change. Il paie le pro, comme aujourd'hui (« À régler au pro, en espèces ou par mobile money »). La commission ne lui est jamais montrée.

## Réalité terrain

- **Confiance du pro.** La commission ne doit jamais être une surprise.
  - Le taux de ses métiers est lisible dans son portefeuille avant qu'il devise. Le taux en vigueur à l'envoi du devis s'applique, même si l'Ops le change ensuite (ADR 0012).
  - Chaque commission est rattachée à une mission (métier, date, montant, taux). Pas de ligne « frais divers ».
  - Pas de suspension automatique pour dette, pas de pénalité de retard. La seule conséquence automatique est le blocage des nouveaux devis, annoncé par une alerte avant.
- **Contournement.** Une commission sur le cash pousse à régler hors plateforme. Contre-mesures : taux modéré, plafond par mission (Q1, Q2), et une commission qui s'applique aussi aux fins sans code (Q4), pour que le repli `no_code` ne serve pas à l'éviter.
- **Paiement.** Le pro paie vers un numéro marchand Jeflink. Le canal (Wave, Orange Money) est une donnée saisie par l'Ops, pas une liste en dur. Les frais du canal sont à la charge de Jeflink : le pro est crédité du montant qu'il a envoyé (Q7).
- **Pro sans mobile money.** Il dépose l'argent chez un agent Wave ou Orange Money, vers le numéro marchand, et déclare avec la référence du reçu de l'agent. Les instructions du canal le disent ; aucun code de plus. Les espèces au bureau restent possibles.
- **Pièces.** L'assiette est le montant total, pièces comprises ; le poids des pièces est compensé par un taux plus bas sur les métiers où elles pèsent (froid & clim, électroménager, plomberie : 7 % au lieu de 10 %) et par le plafond.
- **Réseau.** La déclaration exige une `Idempotency-Key` : un renvoi après une coupure ne crée pas deux règlements. Le résumé du portefeuille tient en une petite réponse ; l'historique est paginé par curseur.
- **Littératie.** L'API renvoie des montants entiers et des codes courts. L'app Pro (étape 6) affichera un seul grand chiffre, une liste par mission et un bouton « Payer » qui montre le numéro marchand. Aucune capture d'écran exigée (Q9).
- **Un pro paie parfois depuis le téléphone d'un proche.** Il indique alors les 4 derniers chiffres du numéro payeur, rien de plus.

## Modèle de données et API

### Grand livre (`wallet`, ADR 0012)

`LedgerAccount` : `kind` · `provider` (FK nulle) · `channel` (FK nulle vers `payments.SettlementChannel`) · `last_reminder_at`. Unicité `(kind, provider, channel)`, nulls non distincts. Le compte `pro_commission_due` d'un pro est créé au premier mouvement, sous le verrou de sa fiche ; les comptes de la plateforme par migration de données.

| Compte                                          | Propriétaire          | Sens normal | Rôle                                                                       |
| ----------------------------------------------- | --------------------- | ----------- | -------------------------------------------------------------------------- |
| `pro_commission_due`                            | un pro                | débit       | Créance de Jeflink sur le pro. Positif : le pro doit. Négatif : avoir.     |
| `platform_revenue`                              | Jeflink               | crédit      | Commissions acquises.                                                      |
| `platform_collections`                          | Jeflink, un par canal | débit       | Fonds reçus, à rapprocher du relevé du canal (Wave, Orange Money, caisse). |
| `platform_goodwill`                             | Jeflink               | débit       | Gestes commerciaux.                                                        |
| `client_escrow`, `pro_pending`, `pro_available` | (V2)                  |             | Déclarés, aucune écriture en V1 (test).                                    |

`LedgerTransaction` (`BaseModel`, immuable) : `kind` (`commission`, `settlement`, `reversal`, `goodwill_credit`, `correction_debit`) · `idempotency_key` (unique) · `provider` (FK nulle) · `booking` (FK nulle) · `payment_intent` (FK nulle) · `reverses` (FK nulle vers une transaction) · `reason_code` (24) · `note` (200, Ops seulement, numéros refusés) · `actor` (FK nulle), `actor_kind` (`system`, `ops`, `pro`).

`LedgerEntry` (immuable) : `transaction` · `account` · `side` (`debit`, `credit`) · `amount_xof` (`PositiveBigIntegerField`, > 0) · `created_at`. Index `(account, created_at)`.

| Opération                                            | Débit                     | Crédit                    | Clé d'idempotence          |
| ---------------------------------------------------- | ------------------------- | ------------------------- | -------------------------- |
| Commission à la clôture                              | `pro_commission_due`      | `platform_revenue`        | `commission:<réservation>` |
| Règlement confirmé (canal c)                         | `platform_collections[c]` | `pro_commission_due`      | `settlement:<intention>`   |
| Avoir sur une commission (partiel ou total)          | `platform_revenue`        | `pro_commission_due`      | `reversal:<public_id>`     |
| Contre-passation d'un règlement confirmé à tort      | `pro_commission_due`      | `platform_collections[c]` | `reversal:<public_id>`     |
| Geste commercial                                     | `platform_goodwill`       | `pro_commission_due`      | `goodwill:<public_id>`     |
| Correction en faveur de Jeflink (commission oubliée) | `pro_commission_due`      | `platform_revenue`        | `correction:<public_id>`   |

- **Seul écrivain** : `wallet.services.post_transaction(kind, lines, idempotency_key, …)`. Il vérifie que les montants sont des `int` (jamais `bool`, `float` ni `Decimal`), strictement positifs, au moins deux lignes, débits égaux aux crédits, comptes permis en V1. Il verrouille les comptes du pro par id, après les verrous de l'appelant. Une clé déjà vue rend la transaction existante si le contenu est le même, sinon `ValueError` (bug, pas une erreur d'utilisateur).
- **En base** : triggers d'immuabilité sur les deux tables, et trigger de contrainte différé qui refuse au commit une transaction déséquilibrée ou à une seule ligne.
- **Contre-passation** (`reverse(transaction, amount_xof, reason_code, note, operator)`) : lignes inversées, partielle permise. La somme des contre-passations d'une transaction ne dépasse jamais son montant (vérifié sous verrou).
- **Soldes** (`wallet.selectors`) : `balance(account)` en une agrégation ; `provider_wallet(provider)` rend `due_xof`, `credit_xof`, `pending_xof` (déclarations qui comptent, voir « Seuils de dette »), `effective_due_xof` (`due_xof - pending_xof`, plancher 0) et `state` (`ok`, `alert`, `blocked`).
- **Ordre des verrous** (prolongé) : comptes utilisateurs (par id), fiche pro, demande, réservation, intention de paiement, comptes du grand livre du pro (par id). Les comptes de la plateforme ne sont jamais verrouillés.

### Taux de commission (`wallet.CommissionRate`)

`trade` (FK nulle : taux par défaut) · `rate_bps` (points de base, de 0 à 5 000, `CheckConstraint`) · `cap_xof` (plafond par mission, nul permis, > 0 sinon) · `valid_from` · `note` · `created_by`. Unicité `(trade, valid_from)`.

- **En ajout seul**, comme un journal : l'admin permet d'ajouter, jamais de modifier ni de supprimer. `valid_from` n'est jamais dans le passé (`wallet.services.add_rate`, audit `wallet.rate.added`).
- **Taux initiaux** (Q1) : taux par défaut 1 000 points de base (10 %), plafond 20 000 F, créé par migration de données. 700 points de base (7 %), même plafond, pour `climatisation`, `electromenager` et `plombier` : comme les métiers eux-mêmes, ces taux sont chargés par `seed_reference_data` (`wallet/reference_data.py`), seulement si le métier n'a encore aucun taux. Un métier absent est ignoré.
- **Taux applicable** : le taux du métier de la demande en vigueur à `quote.created_at`, sinon le taux par défaut en vigueur à cette date.
- **Calcul** (fonction pure, testée) : `commission_xof(base_xof, rate_bps, cap_xof) = min(base_xof * rate_bps // 10_000, cap_xof)`. Arrondi à l'entier inférieur, donc en faveur du pro. Aucune division réelle dans `wallet` ni `payments` (test d'architecture sur l'AST).

### Commission à la clôture (`wallet.Commission`)

`booking` (OneToOne) · `provider` · `trade` · `base_xof` · `rate` (FK nulle), `rate_bps`, `cap_xof` (copies) · `amount_xof` (≥ 0) · `status` (`charged`, `exempt`) · `exempt_reason` (`review_account`, `zero_rate`, `zero_amount`, `rate_missing`) · `completion_method`, `close_reason` (copies) · `ledger_transaction` (OneToOne nulle) · `created_at`. Contrainte : `charged` si et seulement si `amount_xof > 0` et une transaction liée. Immuable.

`wallet.services.charge_commission_on_close(booking, reason)` est inscrit par `register_close_handler` dans le `ready()` de `wallet`. Il s'exécute dans la transaction de la clôture, réservation verrouillée.

- **Idempotent** : une `Commission` existe déjà pour la réservation, il ne fait rien (unicité en base, plus clé `commission:<réservation>`).
- **Assiette** : `Booking.amount_xof` à la clôture, donc après les avenants acceptés, frais de déplacement compris (Q3).
- **Selon la fin et le motif de clôture** :

| Cas                                                  | Commission                                                                           |
| ---------------------------------------------------- | ------------------------------------------------------------------------------------ |
| `window_elapsed`, fin par code                       | due                                                                                  |
| `window_elapsed`, fin `no_code` (tous motifs)        | due, comme une fin par code ; `completion_method` copié pour l'Ops (Q4)              |
| `dispute_for_pro`, `dispute_no_fault`                | due                                                                                  |
| `dispute_for_client`                                 | due par défaut ; avoir de l'Ops si le pro a remboursé le client (Q5)                 |
| réservation annulée (dont no-show, désistement, Ops) | aucune : elle n'arrive jamais à `closed`                                             |
| client `is_review_account`                           | `exempt` (`review_account`), sans écriture                                           |
| taux de 0                                            | `exempt` (`zero_rate`), sans écriture                                                |
| montant arrondi à 0 (très petite mission)            | `exempt` (`zero_amount`), sans écriture                                              |
| aucun taux applicable (ne doit pas arriver)          | `exempt` (`rate_missing`), alerte `wallet_rate_missing` ; l'Ops passe une correction |
| pro de démo (`is_demo`, local et test seulement)     | due : le parcours de démo doit montrer la commission                                 |

- Le gestionnaire ne lève jamais d'erreur métier : une clôture ne doit pas rester bloquée par le portefeuille. Une erreur de programmation annule la clôture, que `close_due` retente.
- Après l'écriture, il compare l'état du portefeuille avant et après. S'il franchit un seuil, il notifie (après commit).
- Pas de rattrapage : seules les réservations closes après la migration ont une commission.

### Seuils de dette

Réglages, jamais en dur : `WALLET_DEBT_ALERT_XOF` (10 000), `WALLET_DEBT_BLOCK_XOF` (25 000), `WALLET_REMINDER_EVERY` (7 j). Valeurs validées (Q6).

- **Alerte** : `effective_due_xof` atteint le premier seuil. Notification `wallet.debt_alert`, une fois par franchissement.
- **Blocage** : `effective_due_xof` atteint le second seuil. Nouveaux devis refusés : `409 commission_debt_over_limit`. Notification `wallet.quotes_blocked` (SMS). Le blocage se lève seul quand la dette effective repasse sous le seuil (`wallet.quotes_unblocked`).
- **Ce qui n'est jamais bloqué** : confirmer une réservation déjà acceptée, toute action sur une mission en cours, l'envoi des photos, le litige, la lecture du portefeuille, le règlement.
- **Une déclaration compte comme payée tant que l'Ops n'a pas décidé** (`declared` ou `needs_correction`) : un pro qui vient de payer peut deviser de nouveau sans attendre l'Ops, même si l'Ops tarde (week-end, fêtes). L'alerte `wallet_settlements_overdue` pousse l'Ops ; le retard de Jeflink ne retombe jamais sur le pro. Une déclaration rejetée ne compte plus ; son effet disparaît.
- **Abus fermé** : la confiance se perd par un rejet `not_found`, `duplicate` ou `amount_mismatch`, par une confirmation dont le montant reçu est inférieur au déclaré, ou par la contre-passation d'un règlement. Les déclarations faites ensuite ne comptent plus comme payées. Elle ne revient qu'avec une confirmation dont le montant reçu couvre le déclaré, jamais contre-passée (`payments.services.distrusted_since`, dérivé de l'historique, aucun champ stocké ; revue sécurité). Le renvoi « à corriger » n'est pas un rejet.
- **Mécanisme** : `requests.quotes.register_quote_guard(fn)`, appelé par `submit_quote` avant l'insertion. `wallet` s'y inscrit. `requests` n'importe jamais `wallet` (ADR 0012).
- **Relance** : `wallet.tasks.remind_debts` (quotidienne) notifie `wallet.debt_reminder` aux pros dont la dette effective dépasse le seuil d'alerte, au plus une fois par `WALLET_REMINDER_EVERY` (`LedgerAccount.last_reminder_at`).

### Règlements (`payments`, ADR 0002 et 0012)

**Interface `payments.gateways.PaymentGateway`** (protocole, V1 minimale) : `create_intent(…)`, `confirm(intent, …)`, `refund(…)`, `payout(…)`, `verify_webhook(request)`. Registre `payments.gateways.get_gateway(name)`.

| Adaptateur            | V1                                                                                                                                                         |
| --------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `manual_mobile_money` | `create_intent` : déclaration du pro, statut `declared`. `confirm` : par l'Ops, avec le montant reçu. Ou les deux en un geste par l'Ops, depuis le relevé. |
| `cash`                | `create_intent` et `confirm` en un geste, par l'Ops (espèces remises au bureau, numéro de reçu).                                                           |
| `fake`                | toutes les méthodes, pour les tests ; refusé hors `local` et `test` (contrôle au démarrage).                                                               |
| `wiipay`              | absent (V2).                                                                                                                                               |

`refund`, `payout` et `verify_webhook` lèvent `GatewayOperationUnsupported` pour `manual_mobile_money` et `cash`. Rien d'autre n'est construit pour la V2.

**`payments.SettlementChannel`** (donnée, saisie par `Comptabilité`) : `slug` (figé) · `gateway` (`manual_mobile_money`, `cash`) · `label_fr`, `label_wo` · `account_display` (numéro marchand ou nom du compte Jeflink : pas une donnée personnelle) · `instructions_fr`, `instructions_wo` · `is_active` · `position`. Désactivé plutôt que supprimé.

**`payments.PaymentIntent`** (`BaseModel`) : `purpose` (`commission_settlement` ; d'autres en V2) · `gateway` · `channel` · `provider` · `origin` (`pro_declared`, `ops_recorded`) · `status` (`declared`, `needs_correction`, `confirmed`, `rejected`, `cancelled`) · `declared_xof` · `received_xof` (nul avant confirmation) · `reference` (40, normalisée) · `paid_at` (heure déclarée) · `payer_last4` (vide si payé depuis le numéro du pro) · `receipt_number` (espèces) · `idempotency_key` + `payload_hash` (unique par pro) · `correction_reason` (`reference_not_found`, `amount_mismatch`, `paid_at_mismatch`) · `corrected_at` (nul tant que le pro n'a pas corrigé) · `reject_reason` (`not_found`, `amount_mismatch`, `duplicate`, `other`) · `decided_by`, `decided_at`.

- Unicité `(channel, reference)` sur les intentions non rejetées ni annulées : une même transaction ne règle jamais deux fois. Même règle pour `(channel, receipt_number)` des espèces.
- Référence : 6 à 40 caractères `[A-Za-z0-9._-]`, majuscules, espaces retirés ; refusée si elle ressemble à un numéro (`common.pii.contains_pii`).
- `paid_at` : pas dans le futur, pas plus vieux que `WALLET_SETTLEMENT_MAX_AGE` (30 j).
- Montant déclaré : de 1 à `due_xof - pending_xof`. Au-delà : `422 settlement_exceeds_due`, et le front renvoie vers le support.
- Au plus `WALLET_SETTLEMENT_MAX_PENDING` (3) déclarations en attente par pro, et 10 par 24 h (limite par utilisateur, fermée si Redis tombe).

**Services** (`payments.services`, toute écriture ; `payments` appelle `wallet`, jamais l'inverse) :

- `declare_settlement(provider, actor, channel, amount_xof, reference, paid_at, payer_last4, idempotency_key)` : verrous compte du gérant, fiche, puis création par la passerelle. L'Ops la voit dans la file « à rapprocher » de l'admin. Audit `payments.settlement.declared` (montant, canal ; jamais la référence ni les chiffres).
- `cancel_settlement(intent, actor)` : le pro retire une déclaration encore `declared` ou `needs_correction`, seulement dans les 30 minutes qui suivent sa déclaration ou sa correction (`WALLET_SETTLEMENT_CANCEL_WINDOW`, faute de frappe) ; au-delà, `409 settlement_not_cancellable`. Une référence déjà déclarée par un pro ne lui resert jamais, même retirée ou rejetée (revue sécurité).
- `confirm_settlement(intent, operator, received_xof)` : verrous fiche, intention, puis `gateway.confirm`, puis `wallet.services.record_settlement(intent)`. L'opérateur ne peut pas être le gérant du pro. Un montant reçu différent du déclaré est permis et audité (`difference_xof`). Un excédent devient un avoir sur les prochaines commissions ; son remboursement est hors périmètre.
- `request_correction(intent, operator, reason)` : `declared` → `needs_correction`, une seule fois par déclaration (`corrected_at` nul). Notification `wallet.settlement_needs_correction` (SMS). Ce n'est pas un rejet : la déclaration continue de compter.
- `correct_settlement(intent, actor, reference, amount_xof, paid_at, payer_last4)` : le pro corrige ; mêmes validations que la déclaration ; `needs_correction` → `declared`, `corrected_at` posé. Une seconde demande de correction est refusée : l'Ops confirme ou rejette.
- `reject_settlement(intent, operator, reason, note)`.
- `record_mobile_money_settlement(provider, operator, channel, amount_xof, reference, paid_at, idempotency_key)` : versement vu dans le relevé marchand et venu du numéro du pro, sans déclaration (`origin = ops_recorded`). Passerelle `manual_mobile_money`, création et confirmation dans la même transaction. Même unicité `(channel, reference)` : une déclaration du pro arrivée ensuite pour la même transaction répond `settlement_reference_used`.
- `record_cash_settlement(provider, operator, amount_xof, receipt_number, idempotency_key)` : passerelle `cash`, création et confirmation dans la même transaction.
- Tâche `payments.tasks.watch_settlements` (toutes les heures) : alerte `wallet_settlements_overdue` (`common.alerts.alert_once`) si une déclaration attend depuis plus de `WALLET_SETTLEMENT_REVIEW_SLA` (24 h).

### Ajustements de l'Ops

`wallet.services` : `waive_commission(commission, amount_xof, reason_code, note, operator)` (contre-passation de la commission), `reverse_settlement(intent, reason_code, note, operator)`, `post_goodwill_credit(provider, amount_xof, …)`, `post_correction_debit(provider, amount_xof, booking=None, …)`.

- Motifs codés : `dispute_refund`, `no_payment`, `entry_error`, `goodwill`, `duplicate_settlement`, `other`. Note obligatoire (1 à 200 caractères, numéros refusés), jamais journalisée.
- L'opérateur ne peut pas être le gérant du pro concerné. Audit `wallet.adjustment.posted` (type, montant, motif, transaction ; jamais la note).
- Notification `wallet.adjustment_posted` au pro.

### Admin Django (Ops au début, comme les étapes 3 et 4)

- **Groupes** (migrations, comptes techniques nommés, second facteur) :
  - `Rapprochement` : voir les portefeuilles et le grand livre, confirmer, renvoyer à corriger ou rejeter une déclaration, créditer un versement vu dans le relevé, enregistrer un règlement en espèces.
  - `Comptabilité` : tout ce que voit `Rapprochement`, plus les taux, les canaux, les avoirs, les corrections et les contre-passations.
- **Second facteur redemandé** : chaque action qui écrit dans le grand livre exige un code TOTP saisi depuis moins de `ADMIN_STEP_UP_TTL` (5 min). Nouveau `accounts.admin_site.verify_admin_step_up(user, code)` : même mécanisme que la connexion (anti-rejeu, verrou), audit `accounts.admin.step_up`. Il pose dans la session l'heure de la vérification ; pendant 5 minutes, l'opérateur enchaîne les confirmations sans ressaisir de code. Chaque écriture reste auditée une à une. Le TOTP de connexion, valable 12 h, ne suffit pas ; la fenêtre ne se prolonge pas à l'usage.
- **Écrans** : portefeuilles des pros (dû, en attente, état, filtre « au-dessus du seuil ») ; déclarations (filtre « à rapprocher », plus anciennes d'abord, référence visible ici seulement) ; commissions (filtres `no_code`, `dispute_for_client`, `exempt`) ; grand livre en lecture seule ; taux en ajout seul ; canaux. Aucune suppression nulle part.

### Endpoints

Tag `wallet`. Identifiants en `public_id`. Un objet d'un autre pro répond `404`. Listes en curseur.

| Méthode | Chemin                                      | Permission     | Notes                                                                                                                                                                                                                             |
| ------- | ------------------------------------------- | -------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| GET     | `/api/pro/wallet/`                          | `HasOwnerRole` | `due_xof`, `credit_xof`, `pending_xof`, `effective_due_xof`, `state`, `alert_threshold_xof`, `block_threshold_xof`, `rates[{trade_slug, rate_bps, cap_xof, next?{rate_bps, cap_xof, valid_from}}]`, `channels[]`. Suspendu admis. |
| GET     | `/api/pro/wallet/entries/`                  | `HasOwnerRole` | Historique : `{id, kind, amount_xof, effect (increase, decrease), created_at, booking?{id, trade_slug, closed_at}, reason_code}`                                                                                                  |
| GET     | `/api/pro/wallet/entries/{id}/`             | `HasOwnerRole` | Détail : pour une commission, assiette, taux, plafond, montant, méthode de fin, avoirs liés                                                                                                                                       |
| GET     | `/api/pro/wallet/settlements/`              | `HasOwnerRole` | Ses déclarations, statut et motif de rejet ; la référence n'y figure qu'en 4 derniers caractères                                                                                                                                  |
| POST    | `/api/pro/wallet/settlements/`              | `HasOwnerRole` | `{channel, amount_xof, reference, paid_at, payer_last4?}`, `Idempotency-Key`. Suspendu admis. `201` ; rejeu `200`                                                                                                                 |
| POST    | `/api/pro/wallet/settlements/{id}/correct/` | `HasOwnerRole` | `{amount_xof, reference, paid_at, payer_last4?}`. Seulement en `needs_correction`, sinon `409 settlement_not_correctable`                                                                                                         |
| POST    | `/api/pro/wallet/settlements/{id}/cancel/`  | `HasOwnerRole` | `409 settlement_not_pending`                                                                                                                                                                                                      |

- `POST /api/pro/requests/{id}/quotes/` gagne `409 commission_debt_over_limit`.
- Pas d'endpoint Ops : la console Ops n'existe pas. Elle utilisera plus tard `HasOpsPerm("ops.wallet.manage", step_up=True)`.
- **Codes d'erreur** : `commission_debt_over_limit`, `settlement_exceeds_due`, `settlement_amount_invalid`, `settlement_reference_invalid`, `settlement_reference_used`, `settlement_pending_limit`, `settlement_not_pending`, `settlement_not_correctable`, `settlement_rate_limited` (429), `paid_at_invalid`, `payer_last4_invalid`, `channel_inactive`, `nothing_due`, `deletion_blocked_wallet_balance`. Libellés `fr` avec le premier écran qui les affiche (app Pro, étape 6).
- **Notifications** (type et `public_id` seulement) : `wallet.debt_alert`, `wallet.quotes_blocked` (SMS), `wallet.quotes_unblocked`, `wallet.debt_reminder`, `wallet.settlement_confirmed`, `wallet.settlement_needs_correction` (SMS), `wallet.settlement_rejected`, `wallet.adjustment_posted`. La référence est le `public_id` du pro, de l'intention ou de la transaction.

### Données personnelles

- `reference` et `payer_last4` : jamais dans un log, un audit, Sentry, une URL ni un message d'erreur. Un test les cherche dans les logs capturés et les audits.
- `payer_last4` est vidé 12 mois après la décision (`WALLET_PAYER_LAST4_RETENTION`, purge quotidienne). Les écritures et les intentions sont gardées pour la comptabilité (durée légale à confirmer, Q11), sans autre donnée personnelle que le lien au pro.
- **Anonymiseur** `wallet`/`payments` : vide `payer_last4`, garde montants, références et écritures.
- **Bloqueur de suppression** : un gérant dont le solde n'est pas nul, ou qui a une déclaration en attente, ne peut pas supprimer son compte (`deletion_blocked_wallet_balance`, Q10). La dette naît dans la transaction où la réservation quitte `ENGAGED` (déjà bloquante) : il n'y a pas de fenêtre entre les deux. La déclaration est créée sous le verrou du compte, comme le veut `register_deletion_blocker`.

### Points de sécurité

- Grand livre : un seul écrivain, triggers d'immuabilité et d'équilibre en base, aucun champ `balance`, aucune division réelle, montants `int` vérifiés. Tests d'architecture sur ces quatre règles.
- Idempotence partout : commission par réservation, règlement par intention, déclaration par `Idempotency-Key`, unicité de la référence par canal.
- Concurrence (tests en transaction réelle) : deux confirmations d'une même déclaration, clôture et avoir simultanés, deux déclarations avec la même référence, garde des devis pendant une confirmation.
- Admin : groupes dédiés, TOTP frais (moins de 5 minutes) pour chaque écriture, opérateur différent du pro, audit de chaque décision.
- Un pro ne voit que son portefeuille ; la référence complète n'est visible que de l'Ops.
- Revue `security-reviewer` une fois sur la feature (tâches [sécu]).

## IA (si applicable)

Aucune. Aucune décision financière n'est prise par l'IA (PRODUCT.md §5). Un rapprochement assisté des relevés pourra venir plus tard, toujours validé par l'Ops.

## Hors périmètre

- Paiement en ligne, séquestre, Garantie Jeflink, adaptateur WiiPay, webhooks (V2).
- Versements aux pros (`payout`), remboursement d'un client, remboursement d'un trop-perçu au pro.
- Déduction de la dette sur un paiement en ligne (V2, PRODUCT.md §5).
- Abonnement Pro+, période de gratuité par pro, commission par zone, pénalités de retard, suspension automatique pour dette (jamais automatique).
- Écran portefeuille du pro : app Pro (étape 6). Console Pro et console Ops (pas encore construites ; Q8).
- Rapprochement automatique par import de relevé, exports comptables, facture de commission au pro, traitement fiscal (Q12).
- Mode de paiement du client (espèces ou mobile money) enregistré à la fin de mission.
- Collecte d'espèces par des agents sur le terrain.

## Critères d'acceptation

- [ ] En local, de bout en bout : une réservation de `demo_pro` est close par `close_due` ; `GET /api/pro/wallet/` montre la commission au taux du devis ; `demo_pro pay` déclare un règlement ; le compte `Rapprochement` le confirme dans l'admin avec un TOTP frais ; le solde revient à 0.
- [ ] Au-delà de `WALLET_DEBT_BLOCK_XOF`, un nouveau devis répond `409 commission_debt_over_limit`, mais la confirmation d'une réservation acceptée et la fin d'une mission en cours passent. Une déclaration en attente lève le blocage, quel que soit son âge, tant que l'Ops n'a pas décidé ; son rejet le rétablit. Après un rejet `not_found`, une nouvelle déclaration ne le lève plus avant confirmation.
- [ ] Chaque transaction est équilibrée : test de propriété sur des suites aléatoires de commissions, règlements, avoirs et contre-passations (somme de tous les comptes nulle, solde du pro égal à commissions moins règlements plus corrections moins avoirs). Une transaction déséquilibrée écrite en SQL brut est refusée au commit ; une mise à jour ou une suppression aussi.
- [ ] Le gestionnaire de clôture appelé deux fois n'écrit qu'une commission. Chaque cas du tableau (code, `no_code`, trois décisions de litige, compte de revue, taux 0, taux manquant) a son test. Un taux ajouté après le devis ne change pas la commission.
- [ ] `commission_xof` : entier, entre 0 et l'assiette, croissant avec l'assiette, plafond respecté ; arrondi à l'entier inférieur sur des cas limites.
- [ ] Un renvoi « à corriger » laisse la déclaration compter ; le pro corrige une fois, une seconde demande de correction est refusée. Un versement crédité par l'Ops depuis le relevé ramène le solde sans déclaration du pro.
- [ ] Une même référence ne règle jamais deux fois sur un canal. Un rejeu de déclaration ne crée rien de plus. L'opérateur ne peut pas confirmer pour son propre compte pro.
- [ ] Les tests d'architecture passent : aucune écriture de `LedgerEntry` ni de `LedgerTransaction` hors `wallet/services.py`, aucun champ `balance`, aucune division réelle ni `float` dans `wallet` et `payments`, aucune écriture sur les comptes de la V2.
- [ ] Référence et 4 derniers chiffres absents des logs et des audits. Anonymiseur, purge et bloqueur de suppression testés.
- [ ] `make openapi` à jour, client TS régénéré.

## Tâches par couche

Chacune livrable et testable seule, dans l'ordre. `make openapi` à chaque tâche qui touche l'API.

- api :
  1. [sécu] **Socle `wallet`** : app, `LedgerAccount`, `LedgerTransaction`, `LedgerEntry`, migrations (triggers d'immuabilité, trigger d'équilibre différé, comptes de la plateforme), `post_transaction`, `reverse`, sélecteurs de solde, admin en lecture seule, tests de propriété et d'architecture.
  2. **Taux** : `CommissionRate`, `add_rate`, taux par défaut par migration de données (10 %, plafond 20 000 F), taux de lancement par métier dans `seed_reference_data` (7 % : `climatisation`, `electromenager`, `plombier`), `rate_for(trade, at)`, `commission_xof` pure, admin en ajout seul, groupe `Comptabilité` (migration), schéma d'audit.
  3. [sécu] **Commission à la clôture** : `Commission`, `charge_commission_on_close` inscrit par `register_close_handler`, cas du tableau, franchissement de seuils et notifications, tests d'idempotence et de concurrence avec `close_due` et `resolve_dispute`.
  4. [sécu] **Socle `payments`** : app, protocole `PaymentGateway`, registre, adaptateurs `manual_mobile_money`, `cash`, `fake` (contrôle au démarrage hors local et test), `SettlementChannel` et son admin, `PaymentIntent`, tests de l'interface.
  5. [sécu] **Règlements** : `declare_settlement`, `cancel_settlement`, `confirm_settlement`, `request_correction`, `correct_settlement`, `reject_settlement`, `record_mobile_money_settlement`, `record_cash_settlement`, `record_settlement` côté `wallet`, `verify_admin_step_up` (fenêtre de 5 min), admin `Rapprochement` (migration du groupe, page TOTP), `watch_settlements`, notifications, limites, tests de concurrence.
  6. [sécu] **Ajustements** : `waive_commission`, `reverse_settlement`, `post_goodwill_credit`, `post_correction_debit`, actions d'admin `Comptabilité` avec TOTP, audits, notifications.
  7. **Seuils et garde des devis** : `register_quote_guard` dans `requests.quotes`, inscription de `wallet`, `409 commission_debt_over_limit`, levée par déclaration en attente tant que l'Ops n'a pas décidé, sauf après un rejet `not_found` ou `duplicate`, `remind_debts`, réglages `WALLET_*`.
  8. [sécu] **API pro** : résumé, historique et détail, déclarations (liste, création, correction, retrait), sérialiseurs (référence tronquée), tests autorisé, refusé (autre pro : 404) et invalide, `make openapi`.
  9. **Données personnelles** : anonymiseur, bloqueur de suppression, purge de `payer_last4`, test d'absence dans les logs et les audits.
  10. **Démo** : `demo_pro wallet` (résumé et historique), `demo_pro pay --amount … --channel …` (déclaration avec une référence factice), `seed_settlement_channels` (canaux factices) ; `DJANGO_ENV=local` seulement.
  11. **Documentation** : ARCHITECTURE.md (§ Argent : comptes, écritures, ordre des verrous ; domaines `wallet` et `payments`), `apps/api/CLAUDE.md` (conventions argent, registre de garde des devis), `chantier-prod.md`, ADR 0012 passé à « accepté ».
- web : rien. La commission n'est jamais montrée au client ; la mention « À régler au pro » de la spec 003 suffit.
- console : rien (pas encore construite ; l'Ops travaille dans l'admin Django).
- client / pro : rien avant l'étape 6 ; le client TS régénéré suffit. L'écran portefeuille de l'app Pro (solde, historique, « Payer », déclaration) et les libellés `fr` des codes d'erreur y entrent.

## Revue terrain et arbitrages (2026-10-05)

La revue `terrain-reviewer` a relevé six points bloquants et onze ajustements. Zay a tranché :

- **Assiette (B5, Q1, Q3).** Montant total convenu, pièces et déplacement compris. Le poids des pièces est compensé par le taux : 10 % par défaut, 7 % pour `climatisation`, `electromenager` et `plombier`, plafond 20 000 F par mission. L'argument de la Q3 est corrigé : le déplacement est calculé sur la distance réelle (PRODUCT.md), il ne se gonfle pas ; l'assiette totale est retenue parce qu'elle est plus simple à expliquer et ne pousse pas à déplacer de la main-d'œuvre vers la ligne « pièces ».
- **Déclaration en attente (B1).** Elle compte comme payée tant que l'Ops n'a pas décidé, sans limite de 72 h. Après un rejet `not_found` ou `duplicate`, les déclarations suivantes ne comptent qu'une fois confirmées.
- **Délai de grâce, SMS à 80 %, seuils en données (B3, B4).** Non retenus en V1. Les seuils restent des réglages : 10 000 F (alerte) et 25 000 F (blocage). Une pause pendant les fêtes passe par un changement de réglage.
- **Chemin de paiement (A1, B2).** L'Ops crédite un versement vu dans le relevé et venu du numéro du pro, sans déclaration. La déclaration garde la référence obligatoire ; un renvoi « à corriger » permet au pro de corriger une fois.
- **Superutilisateur (revue sécurité, constat 11).** Il peut cumuler les rôles `Rapprochement` et `Comptabilité` : aucune séparation imposée pour ce compte technique.
- **Second facteur (A7).** Un code TOTP frais ouvre une fenêtre de 5 minutes ; chaque écriture reste auditée.
- **Pros sans mobile money (Q7).** Dépôt chez un agent Wave ou Orange Money vers le numéro marchand, décrit dans les instructions du canal. Espèces au bureau toujours possibles.
- **Garde-fou de mise en service (B6).** Aucun vrai pro n'est facturé avant l'écran portefeuille de l'étape 6 : en production, taux par défaut à 0 jusque-là (ajouté à `chantier-prod.md`).
- **Q5.** Le litige n'enregistre aucun remboursement en V1 (`trust.Dispute`) : l'avoir `dispute_refund` reste une décision manuelle de l'Ops.
- **Q2, Q4, Q8 à Q13.** Propositions acceptées telles quelles. Q12 : le taux est tout compris (TTC), donc `commission_xof` ne change pas ; la ventilation fiscale reste à valider avec un comptable (`chantier-prod.md`).

**Pour l'étape 6 (app Pro), retenus de la revue** : montant prérempli avec la dette et heure en « à l'instant, aujourd'hui, hier » (A2) ; `Idempotency-Key` créée à l'ouverture de l'écran et gardée sur l'appareil, canaux en cache, brouillon « en cours d'envoi » (A3) ; aperçu du net dans le formulaire de devis et taux à venir (`next`, A5) ; vocabulaire « Part de Jeflink à envoyer », jamais « dette », « avoir » ni « contre-passation », libellés `wo` et message vocal (A6) ; qui a clôturé chaque mission, pour le gérant d'une entreprise (A8) ; explication d'un versement supérieur au dû (A11).

**Écartés ou reportés** : remise des petites dettes à la suppression du compte (A9) et procédure de changement de numéro (A10), à reprendre avec les procédures support (`docs/ops/`) ; SMS pour la confirmation et l'alerte (A4) : `settlement_needs_correction` et `quotes_blocked` partent en SMS, les autres en notification simple.

## Décisions (Zay, 2026-10-05)

1. **Q1 — Taux.** 10 % par défaut ; 7 % pour `climatisation`, `electromenager`, `plombier`. Ajustables par métier sans déploiement. Le taux du devis fait foi, arrondi à l'entier inférieur.
2. **Q2 — Plafond.** 20 000 F par mission, pour tous les métiers.
3. **Q3 — Assiette.** Montant total convenu, déplacement et pièces compris.
4. **Q4 — Fin sans code.** Commission due ; avoir de l'Ops (`no_payment`) si le pro n'a pas été payé.
5. **Q5 — Litige pour le client.** Commission maintenue ; avoir manuel de l'Ops (`dispute_refund`) si le pro a remboursé.
6. **Q6 — Seuils.** Alerte à 10 000 F, blocage des nouveaux devis à 25 000 F, levée automatique ; une déclaration compte jusqu'à la décision de l'Ops. Pas de délai de grâce en V1.
7. **Q7 — Moyens de règlement.** Wave et Orange Money vers un numéro marchand, depuis le téléphone ou chez un agent ; crédit direct par l'Ops depuis le relevé ; espèces au bureau avec reçu. Frais du canal à la charge de Jeflink.
8. **Q8 — Écran du pro.** API et commandes de démo seulement ; l'écran arrive avec l'app Pro (étape 6).
9. **Q9 — Validation.** Groupe `Rapprochement`, alerte au-delà de 24 h, TOTP frais valable 5 minutes, jamais sur son propre compte pro, sans capture d'écran.
10. **Q10 — Suppression avec solde non nul.** Refusée (« Réglez votre solde ou contactez le support »).
11. **Q11 — Conservation.** 10 ans, à confirmer avec le comptable, déclaré à la CDP.
12. **Q12 — Fiscalité.** Taux tout compris en V1 ; TVA et facture de commission validées avec un comptable avant la mise en ligne.
13. **Q13 — Lancement sans commission.** Rien de spécial dans le code : un taux à 0 avec date de fin suffit.
