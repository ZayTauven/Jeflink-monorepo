# ADR 0012 — Grand livre : journal équilibré en base, commission au taux du devis, règlements par intention de paiement

Statut : accepté · 2026-10-05 (proposé le 2026-10-04) · Spec : `docs/specs/005-wallet-commission.md` · Précise l'ADR 0002

## Contexte

L'ADR 0002 pose le principe : tout mouvement d'argent est une écriture en partie double dans `wallet.LedgerEntry`, en entiers XOF, et tout paiement passe par `PaymentGateway`. La spec 005 écrit les premiers mouvements : la commission due par le pro sur une mission payée en espèces ou en mobile money, puis le règlement de cette dette. Il faut fixer maintenant ce qui sera coûteux à changer plus tard :

- la forme du journal (un mouvement = combien de lignes, quel signe) et ce qui garantit l'équilibre ;
- comment empêcher toute modification d'une écriture passée ;
- l'ordre des verrous, car la commission s'écrit dans la transaction de clôture de la réservation (spec 004), qui tient déjà trois verrous ;
- quel taux s'applique quand l'Ops le change ;
- comment un règlement déclaré à la main en V1 deviendra un paiement WiiPay en V2 sans réécriture.

## Décision

- **Journal en deux tables.** `LedgerTransaction` (l'en-tête : type, clé d'idempotence unique, pro, réservation ou intention de paiement liée, motif, acteur) et `LedgerEntry` (une ligne : compte, côté `debit` ou `credit`, `amount_xof` strictement positif). Une transaction a au moins deux lignes, et la somme des débits égale celle des crédits. Pas de montant signé : la convention `PositiveBigIntegerField` de `apps/api/CLAUDE.md` est gardée.
- **Garanties en base, pas seulement dans le code.**
  - Deux triggers PostgreSQL refusent toute mise à jour et toute suppression sur les deux tables (comme `BookingEvent`).
  - Un trigger de contrainte différé (`DEFERRABLE INITIALLY DEFERRED`) vérifie au commit que chaque transaction écrite est équilibrée et compte au moins deux lignes.
  - Une erreur se corrige par une écriture de contre-passation, jamais par une modification.
- **Soldes dérivés.** Le solde d'un compte est la somme de ses lignes, calculée à la lecture. Aucun champ `balance` dans aucun modèle (test d'architecture). Un cache de solde pourra venir plus tard, jamais comme source de vérité.
- **Un seul écrivain.** `wallet.services.post_transaction()` est la seule fonction qui crée des lignes. Les autres services (`charge_commission_on_close`, `record_settlement`, `reverse`, ajustements) l'appellent. Un test d'architecture interdit `LedgerEntry` et `LedgerTransaction` en écriture ailleurs.
- **Comptes du grand livre (`LedgerAccount`).** En V1 : `pro_commission_due` (un par pro, créé au premier mouvement), `platform_revenue`, `platform_collections` (un par canal de règlement) et `platform_goodwill`. `client_escrow`, `pro_pending` et `pro_available` sont déclarés pour la V2, sans aucune écriture en V1 (test).
- **Ordre des verrous prolongé.** Comptes utilisateurs (par id), fiche pro, demande, réservation, intention de paiement, comptes du grand livre du pro (par id). Les comptes de la plateforme ne sont jamais verrouillés : aucun seuil ne dépend de leur solde, et un verrou sur `platform_revenue` sérialiserait toutes les clôtures.
- **Taux de commission en données, en ajout seul.** `CommissionRate` (taux par défaut, ou par métier, en points de base, plafond facultatif, date d'effet jamais dans le passé). On n'en modifie ni n'en supprime aucun : un nouveau taux remplace l'ancien à sa date d'effet. **Le taux en vigueur à l'envoi du devis s'applique**, même si le montant change ensuite par avenant. Le calcul est une fonction pure en entiers (`base * taux // 10 000`, puis plafond).
- **Règlement = intention de paiement.** Le pro qui règle sa dette crée un `payments.PaymentIntent` (objet `commission_settlement`) par la passerelle du canal (`manual_mobile_money` ou `cash` en V1). L'Ops le confirme, et `payments.services` appelle alors `wallet.services.record_settlement()`. En V2, WiiPay confirmera la même intention par webhook, sans toucher à `wallet`. Les appels vont dans un seul sens : `payments` appelle `wallet`, jamais l'inverse.
- **Garde des devis par registre.** `requests.quotes.register_quote_guard(fn)`, comme `register_close_handler` et `register_suspension_handler` : `requests` n'importe jamais `wallet`.

## Conséquences

- Un grand livre déséquilibré ou modifié est impossible, même par un script ou une migration maladroite. Les tests qui touchent le journal tournent en transaction réelle (trigger différé).
- Le pro sait, avant d'envoyer un devis, quel taux s'appliquera. Un changement de taux ne touche jamais une mission déjà devisée.
- Brancher WiiPay en V2 = un adaptateur et un webhook. La déduction de la dette sur un paiement en ligne sera une écriture de plus, entre `pro_pending` et `pro_commission_due`.
- − Les soldes sont recalculés à chaque lecture. Le volume de la V1 le permet ; il faudra mesurer avant la V2.
- − Corriger une erreur demande une contre-passation et un motif : plus lourd qu'une modification, mais c'est le but.
- − Deux triggers et un trigger différé à maintenir dans les migrations, avec leurs tests.

## Alternatives écartées

- **Montant signé sur une seule ligne par compte** : plus court, mais contraire à la convention `PositiveBigIntegerField` et moins lisible pour un comptable.
- **Champ `balance` sur la fiche pro, mis à jour à chaque mouvement** : interdit par la règle 2 de `CLAUDE.md`, et source classique d'écarts.
- **Taux lu à la clôture** : un changement de taux toucherait des missions déjà devisées. Le pro ne peut pas le prévoir.
- **Taux dans `catalog.Trade`** : le catalogue ne porte pas d'argent, et on perdrait l'historique des taux.
- **Règlement saisi directement dans `wallet`, sans intention de paiement** : plus simple en V1, mais à refaire pour WiiPay, et contraire à la règle 3.
