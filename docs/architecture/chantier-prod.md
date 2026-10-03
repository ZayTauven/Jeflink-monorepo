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

| Besoin                                                                                                                                                                                                 | Source              |
| ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ------------------- |
| Cache CDN des endpoints publics `/api/catalog/*` et `/api/zones/*` (réponses anonymes seulement, jamais avec `Authorization`), purge après une saisie dans l'admin                                     | spec 002, api 4     |
| Admin Django modifiable (`catalog`, `zones`) : vérifier qu'il reste sur l'hôte interne, et prévoir l'accès de l'Ops qui saisit (VPN ou équivalent)                                                     | spec 002, Q6        |
| Pages publiques du web servies depuis le cache (ISR) : régler la revalidation et le comportement si l'API ne répond pas                                                                                | spec 002, web 1     |
| Retirer `Accept-Language` du `Vary` des endpoints publics du catalogue (ajouté par `LocaleMiddleware`, alors que la réponse ne dépend pas de la langue, ADR 0009), pour ne pas fragmenter le cache CDN | spec 002, api 4     |
| Supervision de Celery beat : l'expiration des demandes et des devis, et l'annulation des réservations non confirmées, en dépendent (alerte si beat s'arrête ou prend du retard)                        | spec 003, api 3 à 5 |
