# ADR 0002 — Paiements derrière une interface, argent en grand livre

Statut : accepté · 2026-09-30

## Contexte

WiiPay (agrégateur interne) n'est pas prêt. La V1 doit tourner en cash et mobile money déclaré, sans réécriture à l'arrivée de WiiPay.

## Décision

Interface `PaymentGateway` avec adaptateurs (`cash`, `manual_mobile_money`, `fake`, puis `wiipay`). Tous les mouvements d'argent sont des écritures en partie double dans `wallet.LedgerEntry`. Montants en entiers XOF.

## Conséquences

- Brancher WiiPay = écrire un adaptateur.
- Commission sur cash traçable (dette du pro).
  − Plus de rigueur au départ que de simples champs `balance`.
