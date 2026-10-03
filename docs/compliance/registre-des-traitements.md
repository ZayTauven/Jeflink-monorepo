# Registre des traitements — comptes et connexion

Périmètre : domaine `accounts` (spec 001), V1. Document de travail pour le consultant juridique de Jeflink et la déclaration auprès de la CDP (loi sénégalaise n° 2008-12 sur les données à caractère personnel). Les mentions **« à valider »** attendent l'avis du consultant (Q8). Les durées sont des réglages (`AUTH_RETENTION`) : les modifier ne demande aucun développement.

Responsable du traitement : Jeflink (raison sociale et adresse à compléter).
Sous-traitants pressentis : fournisseur SMS (choix en cours, Q7), hébergeur (à choisir), Sentry pour les erreurs techniques (configuré sans donnée personnelle).

## Traitements

### 1. Création et gestion des comptes

| Élément       | Contenu                                                                                                                                                                                            |
| ------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Finalité      | Permettre à un client ou à un pro de se connecter et d'utiliser le service.                                                                                                                        |
| Personnes     | Clients, prestataires, techniciens, équipe Ops.                                                                                                                                                    |
| Données       | Numéro de téléphone (identifiant), nom affiché (facultatif), e-mail (facultatif, jamais vérifié ni utilisé pour récupérer un compte), langue, version et date d'acceptation des conditions, rôles. |
| Base légale   | Exécution du contrat (conditions d'utilisation) — à valider.                                                                                                                                       |
| Durée         | Tant que le compte existe. À la suppression, le compte est anonymisé : numéro, nom et e-mail effacés, la ligne reste sans rien d'identifiant.                                                      |
| Destinataires | Équipe Ops habilitée (numéro masqué par défaut ; numéro complet seulement pour Support et Admin, avec motif tracé et quota).                                                                       |

### 2. Envoi des codes de connexion par SMS

| Élément       | Contenu                                                                                                                                                                                      |
| ------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Finalité      | Vérifier que la personne détient le numéro.                                                                                                                                                  |
| Données       | Numéro de téléphone, transmis au fournisseur SMS. Le SMS ne contient qu'un code et le nom Jeflink, jamais de donnée d'un utilisateur. Le code n'est stocké qu'en empreinte (HMAC).           |
| Base légale   | Exécution du contrat — à valider.                                                                                                                                                            |
| Durée         | Challenges et envois : 7 jours.                                                                                                                                                              |
| Destinataires | Fournisseur SMS (sous-traitant). **Transfert hors du Sénégal si le fournisseur traite à l'étranger : formalité CDP à prévoir** ; contrat de sous-traitance (DPA) exigé du fournisseur (S22). |

### 3. Sessions d'appareil

| Élément  | Contenu                                                                                                                                                                             |
| -------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Finalité | Garder l'utilisateur connecté sans nouveau SMS, lui montrer ses appareils et lui permettre d'en déconnecter un.                                                                     |
| Données  | Libellé de l'appareil (« Samsung A05 »), plateforme, identifiant d'installation aléatoire, dates de connexion et de dernière activité. **Aucune adresse IP n'est conservée** (Q16). |
| Durée    | Session active : 60 j d'inactivité et 180 j au plus sur mobile (30 j et 90 j sur le web). Session révoquée ou expirée : supprimée après 90 jours.                                   |

### 4. Sécurité et prévention de la fraude

| Élément     | Contenu                                                                                                                                                                                                                       |
| ----------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Finalité    | Limiter les abus : envois massifs de SMS, essais de codes, prise de contrôle d'un numéro recyclé.                                                                                                                             |
| Données     | Compteurs pseudonymisés (HMAC du numéro, de l'identifiant d'installation, regroupement d'IP) dans Redis, pour des durées d'une heure à un jour ; blocage temporaire d'un numéro (HMAC seulement) ; marque « compte dormant ». |
| Base légale | Intérêt légitime (sécurité du service et des utilisateurs) — à valider.                                                                                                                                                       |
| Durée       | Compteurs : 1 h à 24 h. Blocages : supprimés 24 h après leur échéance.                                                                                                                                                        |

### 5. Journal d'audit

| Élément     | Contenu                                                                                                                                                                                             |
| ----------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Finalité    | Tracer les actions sensibles (connexion, rôles, actions Ops, suppression) pour enquêter en cas de fraude ou de litige.                                                                              |
| Données     | Acteur, action, compte visé (identifiant interne), date. Numéros seulement masqués ou en HMAC. Notes libres des Ops filtrées (refus d'un numéro, d'un e-mail ou d'une suite de 7 chiffres ou plus). |
| Base légale | Intérêt légitime et obligations de sécurité — à valider.                                                                                                                                            |
| Durée       | 5 ans (à valider). Journal en ajout seul : la purge passera par un archivage dédié, à prévoir avant la production.                                                                                  |

### 6. Second facteur de l'équipe Ops et de l'équipe technique

| Élément  | Contenu                                                                                                                                            |
| -------- | -------------------------------------------------------------------------------------------------------------------------------------------------- |
| Finalité | Protéger les accès à fort pouvoir (console Ops, administration technique).                                                                         |
| Données  | Secret TOTP chiffré, horodatages des échecs (24 h).                                                                                                |
| Durée    | Tant que la personne a le rôle ; effacé au retrait du rôle ou à la réinitialisation. Jetons d'enrôlement et challenges : 7 jours après expiration. |

### 7. Invitations à rejoindre une équipe pro

| Élément     | Contenu                                                                                                                                                                                                          |
| ----------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Finalité    | Permettre à un prestataire d'inviter un technicien.                                                                                                                                                              |
| Personnes   | **Personnes qui ne sont pas encore utilisatrices** : le numéro de l'invité est saisi par le pro.                                                                                                                 |
| Données     | Numéro de l'invité, nom proposé par le pro. L'invité reçoit un SMS générique (sans le nom du pro) ; au plus 2 SMS d'invitation par numéro et par jour ; plus de SMS du même pro pendant 30 jours après un refus. |
| Base légale | Intérêt légitime du pro et de l'invité — **à valider, information de l'invité à prévoir** (mention dans le SMS ou à la première connexion).                                                                      |
| Durée       | Numéro effacé dès que l'invitation est acceptée, refusée ou expirée (7 jours) ; invitation close supprimée après 30 jours (seul un HMAC du numéro reste jusque-là).                                              |

### 8. Changement de numéro par l'Ops

| Élément  | Contenu                                                                                                                                                             |
| -------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Finalité | Rendre son compte à une personne qui a perdu son numéro définitivement.                                                                                             |
| Données  | Nouveau numéro (jusqu'à la clôture de la demande), motif et note de l'Ops, identité des deux Ops pour un compte pro. L'ancien numéro reçoit deux SMS d'information. |
| Durée    | Nouveau numéro effacé à la clôture (24 h au plus) ; demande close supprimée après 30 jours.                                                                         |

### 9. Suppression du compte

| Élément        | Contenu                                                                                                                                                                                                                                                                                                                                                  |
| -------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Finalité       | Droit à l'effacement, exigé aussi par Apple et Google.                                                                                                                                                                                                                                                                                                   |
| Fonctionnement | Libre-service dans l'app, avec un code SMS. Anonymisation immédiate : numéro, nom, e-mail, appareils effacés ; sessions, rôles, codes, invitations et demandes en cours supprimés ou clos ; le numéro redevient libre. Refus possible tant qu'une réservation ou un solde est en cours (domaines futurs), ou pendant 72 h après un changement de numéro. |

### 10. Compte de revue des stores

Compte de test sur une carte SIM détenue par Jeflink, ouvert seulement pendant la revue d'une version par Apple ou Google (45 jours au plus). Aucune personne réelle ; ses données ne sont jamais montrées aux vrais pros.

## Droits des personnes

| Droit                  | Comment                                                                                       |
| ---------------------- | --------------------------------------------------------------------------------------------- |
| Accès                  | Écran « Mon compte » (profil, appareils connectés) ; demande au support pour le reste.        |
| Rectification          | Nom, e-mail et langue dans l'app ; numéro par le support (procédure de changement de numéro). |
| Effacement             | « Supprimer mon compte » dans l'app.                                                          |
| Opposition, limitation | Demande au support — procédure à préciser avec le consultant.                                 |

## Sauvegardes et effacement effectif

Une suppression efface les données de la base en service, pas des sauvegardes déjà faites. L'effacement n'est donc complet qu'au terme de la rotation des sauvegardes.

- **Durée de conservation des sauvegardes : à fixer avec l'hébergeur** (proposition : 30 jours), et à indiquer dans la politique de confidentialité (« effacement définitif sous 30 jours »).
- **Restauration** : avant de rouvrir le service sur une sauvegarde, rejouer les suppressions survenues depuis sa date. Le journal d'audit (`accounts.user.deleted`, conservé hors de la base restaurée ou réexporté) donne la liste des comptes à anonymiser à nouveau.
- Les sauvegardes sont chiffrées et leur accès est réservé à l'équipe technique (à confirmer avec l'hébergeur).

## Reste à faire avant la production

- Choix du fournisseur SMS et de l'hébergeur ; DPA ; formalité de transfert hors Sénégal si nécessaire.
- Validation des bases légales et des durées par le consultant ; déclaration CDP.
- Information des invités (traitement 7) et mention des durées dans la politique de confidentialité.
- Archivage du journal d'audit au-delà de 5 ans.
