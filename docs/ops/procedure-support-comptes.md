# Procédure support — comptes et connexion

Pour l'équipe Support et les Admin de Jeflink. Chaque action décrite ici se fait dans la console Ops et laisse une trace dans le journal d'audit, avec le motif choisi.

## Les trois règles d'or

1. **Ne jamais demander un code.** Ni le code SMS, ni le code de l'application d'authentification. Jeflink ne demande jamais un code par téléphone ou par WhatsApp. Si un client lit son code à voix haute, raccrocher et le lui rappeler.
2. **Ne jamais transmettre un numéro.** Ni le numéro complet d'un client (il ne s'affiche que pour Support et Admin, avec un motif), ni le nouveau numéro d'une demande de changement : quiconque le connaît peut épuiser les codes envoyés.
3. **Note sans donnée personnelle.** La note d'une action ne contient ni numéro, ni e-mail, ni numéro de pièce d'identité : la console la refuse de toute façon.

## « Je ne reçois pas le code »

1. Vérifier avec la personne : bon numéro (attention aux téléphones à deux SIM), réseau, attente de 3 minutes.
2. Si la fiche indique un **blocage OTP** (trop de codes faux), vérifier que c'est bien la personne (réservations récentes, nom), puis **Lever le blocage** (motif « Utilisateur vérifié »). Si le blocage vient d'une attaque (essais par un tiers), motif « Faux positif ».
3. Sinon, transmettre à l'équipe technique (problème de délivrabilité de l'opérateur).

## « J'ai perdu mon téléphone » (même numéro)

L'opérateur remplace la carte SIM avec le même numéro : rien à faire côté Jeflink pour le numéro.

- Si la personne s'est reconnectée sur un nouvel appareil, elle déconnecte l'ancien elle-même (« Mon compte › Appareils connectés »).
- Si elle n'a plus aucun appareil : vérifier son identité (réservations récentes), puis **Déconnecter tous les appareils** (motif « Appareil perdu »).

## « Ce numéro a peut-être changé de propriétaire » (compte dormant)

Quand un compte n'a servi depuis plus de 60 jours et qu'un nouvel appareil s'y connecte, l'app propose deux choix : « Repartir de zéro » (recommandé, sans le support) ou « C'est bien mon compte » (contact du support).

Pour « C'est bien mon compte », la preuve doit être **plus forte que pour une connexion ordinaire**, car le numéro a pu être réattribué :

- **client** : décrire au moins deux réservations passées (métier, quartier, mois, montant approximatif) **et** une information que seul le titulaire connaît (nom d'un pro venu chez lui, référence d'un paiement mobile money). Une seule réservation récente ne suffit pas ;
- **pro (gérant ou technicien)** : vérification par le dossier KYC (pièce, selfie). **Seul un Admin peut lever la restriction d'un compte pro.**

Une fois vérifié : **Lever la restriction** (motif « Titulaire vérifié » ou « KYC vérifié »). En cas de doute, ne rien lever et proposer « Repartir de zéro ».

## Changement de numéro (numéro perdu pour de bon)

Réservé au groupe **Admin**.

1. **Preuve** :
   - client : réservations récentes décrites comme ci-dessus ;
   - pro : contrôle par le dossier KYC.

   **Sans preuve rattachée au compte, proposer de créer un nouveau compte.**

2. **Demande** : console › compte › « Changer le numéro », avec le nouveau numéro et le motif. L'ancien numéro reçoit aussitôt une alerte.
3. **Compte pro** : un **second Admin**, différent du premier, approuve en **ressaisissant le nouveau numéro complet** (celui du dossier). Il ne l'approuve jamais à partir du numéro masqué.
4. **Code** : il part vers le nouveau numéro. Dire à la personne : « Ouvrez l'app, choisissez **J'ai changé de numéro** et saisissez le code. **Ne vous connectez pas avec le nouveau numéro avant** : cela créerait un compte vide. » Le code ne doit jamais être lu au support.
5. Si le SMS n'arrive pas : **Renvoyer le code** (3 codes au plus, une minute entre deux).
6. Après la confirmation, toutes les anciennes sessions sont coupées et l'ancien numéro reçoit une information. Pendant 72 h, le compte ne peut pas être supprimé et les actions d'argent seront bloquées.

Un compte devenu pro pendant la demande repasse automatiquement en attente d'un second Admin.

## Fraude : désactiver, réactiver

- **Désactiver** (motif « Fraude », « Demande de l'utilisateur » ou « Autre ») coupe immédiatement toutes les sessions et ferme une éventuelle demande de changement de numéro.
- Après une désactivation pour **fraude**, seul **un autre Ops** peut réactiver.
- Si une fraude est découverte sur un compte déjà désactivé pour un autre motif, le désactiver à nouveau avec le motif « Fraude » : la règle du second Ops s'applique alors.

## Suppression de compte

Elle se fait dans l'app, par la personne elle-même, avec un code SMS. Le support n'efface jamais un compte. Elle peut être refusée tant qu'une réservation ou un solde est en cours, ou pendant 72 h après un changement de numéro : expliquer le motif affiché par l'app.

## Second facteur de l'équipe Ops (téléphone perdu)

1. L'Ops ne peut plus ouvrir la console. Deux Admin lancent `reset_ops_mfa` (motif « Appareil perdu » ou « Appareil changé ») ; les sessions console de l'Ops sont coupées.
2. Le nouveau **jeton d'enrôlement** (24 h, usage unique) est remis à l'Ops **en main propre ou par un canal distinct de son téléphone**, jamais par WhatsApp.
3. L'Ops se reconnecte, saisit le jeton, scanne la clé et confirme avec un premier code.

Au départ d'un Ops : `revoke_ops_role` efface aussi son second facteur.

## Compte de revue des stores (à chaque soumission Apple ou Google)

Réservé à l'équipe technique et à deux Admin.

1. Régler `OTP_REVIEW_ENABLED_UNTIL` sur la fin prévue de la revue (45 jours au plus) et vérifier que les **deux numéros de revue** (cartes SIM détenues par Jeflink) figurent dans `OTP_REVIEW_ACCOUNTS`.
2. Pour chaque numéro : `create_review_account --phone … --operator … --second-operator … --reason store_submission --token-file …`. La commande crée le compte s'il n'existe pas, lève un éventuel blocage, coupe les anciennes sessions et remet un nouveau code.
3. Saisir le numéro et le code dans la fiche de soumission du store. Utiliser le second numéro pour la démonstration de la suppression de compte.
4. Chaque connexion de l'équipe de revue déclenche une alerte : c'est normal pendant la revue, anormal en dehors.
5. Après la revue, laisser la fenêtre se fermer : les sessions sont coupées automatiquement.

## Administration technique (admin Django)

Accès réservé à l'équipe technique, sur le réseau interne. Chaque compte technique a son second facteur : deux Admin lancent `enroll_admin_totp` et remettent la clé hors bande ; le premier code saisi à la connexion confirme l'appareil.
