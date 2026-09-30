# Spec 001 — accounts : comptes et connexion

Statut : validée · 2026-09-30 (Zay) · ADR liés : 0007 (sessions), 0008 (SmsGateway) · Revues intégrées : `terrain-reviewer` (T1 à T3), `security-reviewer` (S1 à S31)

## Problème

Aucune feature V1 ne démarre sans identité : demandes, devis, réservations, avis, portefeuille pro et KYC s'accrochent tous à un utilisateur. Aujourd'hui, `accounts.User` est un `AbstractUser` vide (username, mot de passe) et DRF tourne en `SessionAuthentication`, ce qui ne convient ni au mobile ni au modèle « téléphone d'abord ». La migration `accounts.0001` peut encore être réécrite tant que rien n'est déployé (ADR 0005) : c'est le moment de poser le bon modèle.

Pour qui :

- **Awa** veut entrer avec son seul numéro, sans mot de passe, et ne plus jamais revoir d'écran de connexion sur son téléphone.
- **Ibou** écrit peu. Le code doit se remplir tout seul depuis le SMS, sa session ne doit pas expirer pendant qu'il travaille hors ligne, et une coupure réseau ne doit jamais le renvoyer au début.
- **Cheikh**, technicien invité par Fatou, doit arriver directement sur ses missions.
- **Moussa** (diaspora) a un numéro non sénégalais. Le modèle doit l'accepter, même si la diaspora n'est ouverte qu'en V3, et il ne doit jamais tomber dans une impasse.
- **L'équipe Ops** a des pouvoirs sensibles (KYC, litiges, ajustements de portefeuille). Un OTP par SMS ne suffit pas : l'échange de carte SIM est une fraude connue.

Objectifs mesurables : connexion complète en moins de 60 s sur un réseau 3G ; au plus 1,3 SMS envoyé par connexion réussie ; aucun SMS pour rouvrir une app tant que la session est active ; aucune déconnexion causée par une coupure réseau.

**Zones sensibles touchées :**

| Zone                                 | Touchée ?                            | Détail                                                                                                                                                                                        |
| ------------------------------------ | ------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Argent (`wallet`, `payments`)        | **Non**                              | Aucun modèle ni aucune écriture. `User.phone_changed_at` et `RequiresRecentAuth` sont posés ici pour que `wallet` impose plus tard 72 h de refroidissement et une réauthentification récente. |
| KYC                                  | **Non**, mais la frontière est posée | Le KYC pro vivra dans `trust`. `accounts` ne fournit que `phone_verified_at`. Aucun statut KYC n'est stocké sur `User`.                                                                       |
| Machine à états des réservations     | **Non**                              | Aucune transition. `HasTechnicianRole` ne vérifie que le rôle ; `IsTechnicianAssigned` (contrôle objet) viendra avec `bookings`.                                                              |
| Auth, sessions, données personnelles | **Oui**                              | **Revue `security-reviewer` obligatoire** avant fusion de chaque tâche [sécu]. Voir « Points de sécurité ».                                                                                   |
| Nouveaux domaines                    | Oui                                  | `trust` (réduit à `AuditEvent`) et `notifications` (réduit à `SmsGateway`), sans autre contenu.                                                                                               |

## Parcours

### Client, première connexion (app `client` et web `/connexion`)

1. **Téléphone.**
   - L'indicatif +221 est présélectionné ; la liste des indicatifs autorisés vient de `GET /api/auth/config/`.
   - Le clavier est numérique et le numéro se met en forme pendant la frappe (`77 123 45 67`).
   - Sous le bouton, une mention courte avec deux liens : « En continuant, vous acceptez les conditions et la politique de confidentialité ».
   - Bouton « Recevoir le code ». L'app génère une `Idempotency-Key` par saisie : un nouvel appui après une coupure ne renvoie pas de SMS (T1).
2. **Code.**
   - L'écran rappelle le numéro en clair (« Code envoyé au 77 123 45 67 · Modifier »), ce qui aide à repérer une faute de frappe ou la mauvaise SIM sur un téléphone double SIM.
   - Pas de compte à rebours. Le message dit : « Le SMS peut mettre 3 minutes ». « Renvoyer le code » apparaît après 60 s. Le champ code reste **toujours actif**, et le remplissage automatique depuis le SMS est prévu (Android, iOS, WebOTP).
   - L'écran distingue « Pas de connexion, on réessaie » de « Code incorrect » et **conserve la saisie** dans les deux cas.
   - **Challenge reprenable** : le mobile garde `challenge_id`, `challenge_secret` (stockage sécurisé), `phone_display` et `expires_at` ; le web les garde en `sessionStorage`. Rouvrir l'app ou l'onglet ramène à l'écran code tant que le challenge vit.
3. **Autres appareils.** Si `verify` renvoie des `other_sessions`, un écran unique s'affiche : « Vous êtes aussi connecté sur Samsung A05 (actif il y a 3 jours). Déconnecter ces téléphones ? » (Oui / Non) (T2).
4. **Nouveau compte seulement :** l'écran demande « Comment doit-on vous appeler ? » avec un seul champ. On peut passer (« Plus tard ») : le compte reste alors **invité**.
5. Arrivée à l'accueil. Ensuite, plus aucune connexion tant que la session vit (voir Sessions).

Sur le web, dans le parcours de demande, l'OTP arrive **au moment de publier**. **Contrainte pour la spec `requests`** : le brouillon de demande est gardé en `localStorage`/IndexedDB (et non en mémoire) pour survivre à la fermeture de l'onglet pendant l'attente du SMS. Il est purgé à la déconnexion.

### Aucune impasse (T3)

- **Numéro hors régions autorisées** : écran dédié, pas une erreur en ligne. « Jeflink est réservé aux numéros du Sénégal pour l'instant. Un proche à Dakar peut commander pour vous. » Deux boutons :
  - « Écrire au support » (WhatsApp) ;
  - « Me prévenir » : ouvre WhatsApp avec un message pré-rempli. Jeflink ne stocke pas le numéro (minimisation). Seul le décompte par région est tracé, sans numéro.
- **Chaque erreur d'auth** (`otp_rate_limited` avec `retry_after` affiché en minutes, `otp_locked`, envois épuisés, `otp_temporarily_unavailable`, `account_disabled`) propose le même lien WhatsApp vers le support, avec un message pré-rempli **sans code ni numéro complet**. Une note vocale est acceptée côté support.
- **Aide « Je ne reçois pas le code »** : 3 pictogrammes (vérifier le numéro, vérifier le réseau, attendre 3 min), un audio court (`fr` ; `wo` dès Q12), puis renvoi et lien support.
- Chaque code d'erreur de l'API a son libellé i18n (`fr`, clé `wo` créée).

### Passer d'invité à complet

L'invité est déjà un `User` : son téléphone est vérifié et `profile_status = guest`. Il n'y a ni compte temporaire ni fusion. Quand une action exige un profil complet, l'API répond `403 profile_incomplete`. L'app affiche alors « Comment doit-on vous appeler ? » puis rejoue l'action.

Proposition : un invité peut créer une demande, recevoir des devis et discuter. Il doit donner son nom pour accepter un devis, laisser un avis ou devenir pro (Q5). **Contrainte pour `requests`/`bookings`** : tant que le client est invité, le pro voit un libellé de repli (par exemple « Client Jeflink · Ouakam »), jamais le numéro.

### Pro (app `pro`)

- Même OTP, habillage Pro, gabarit SMS Pro.
- Après connexion, l'app route selon `roles` (renvoyés par `GET /api/me/`) : `owner` ou `technician` mène à l'espace Pro ; sans rôle pro, l'écran « Devenir pro » s'affiche (contenu : spec `providers`).
- **Cheikh (invitation, S19)** : quand Fatou l'ajoute (spec `providers`), `accounts.services.invite_to_role()` crée une **invitation en attente**. Aucun `User` et aucun `RoleGrant` ne sont créés à ce stade.
  - Cheikh reçoit un SMS générique (lien de l'app, sans le nom de Fatou).
  - Il se connecte par OTP. `verify` renvoie `pending_invitations`, et Cheikh voit « Fatou Nettoyage vous invite comme technicien : Accepter / Refuser ».
  - L'acceptation explicite crée le `RoleGrant` et prévient `providers` (voir Rôles).
  - Si l'invitation porte un nom, l'écran « Comment doit-on vous appeler ? » est sauté. Les conditions sont acceptées à cette première connexion, comme pour tout le monde.
- Un pro reste client : Ibou peut commander un plombier avec le même compte.
- **Contraintes pour les autres specs** : la fiche technicien vue par le client vient de `providers`, pas de `display_name`. Le canal de contact entre client et pro (masqué ou vocal) relève de `bookings`/`messaging`.

### Ops (console `/connexion`)

- OTP SMS, puis second facteur TOTP.
- **Enrôlement (S1)** : il n'est possible qu'avec un **jeton d'enrôlement à usage unique**, remis hors bande par l'équipe technique. Ce jeton est émis par `grant_ops_role` ou `reset_ops_mfa` et vaut 24 h. Sans lui, l'API répond `mfa_enrollment_not_authorized`. L'Ops saisit le jeton, reçoit la clé et l'URI `otpauth://`, puis confirme avec un premier code.
- Sessions : 30 min d'inactivité, 12 h au maximum. Les actions `ops_*_manage` exigent un TOTP de moins de 5 min, redemandé dans une fenêtre modale (step-up).
- Sans TOTP validé, aucune permission Ops ne s'applique, même avec le rôle `ops`.

### Appareil perdu, téléphone partagé, changement d'appareil (T2)

- **Appareil perdu :** l'utilisateur se connecte sur un autre appareil (OTP), puis déconnecte l'ancien, depuis l'écran « Autres appareils » ou depuis « Mon compte › Appareils connectés » (libellé + date de dernière activité). L'effet est immédiat.
- **Plus aucun appareil :** support Ops (WhatsApp), qui révoque toutes les sessions après vérification. **Règle support : aucun agent ne demande jamais un code** (S18).
- **Déconnexion, ou 401 `session_revoked` :** l'app purge le cache hors ligne, les caches TanStack persistés, les brouillons et le jeton push (quand il existe, spec `notifications`).
- **File d'actions hors ligne (app Pro surtout) :**
  - chaque action est marquée du `sub` qui l'a créée et n'est **jamais** rejouée sous un autre compte ;
  - à la déconnexion, s'il reste des actions : « Il reste 3 actions non envoyées. Envoyer d'abord / Supprimer » ;
  - après un `session_revoked`, les actions restent en attente du même `sub`. Si un autre compte se connecte, elles sont supprimées après confirmation.
- **Verrou local optionnel de l'app Pro** (code ou biométrie de l'appareil, `expo-local-authentication`) : voir Q19.

### Numéro perdu pour de bon (changement de numéro, S2)

1. L'utilisateur contacte le support. Une **procédure écrite** s'applique selon le type de compte :
   - client : il doit citer des réservations récentes ;
   - pro : contrôle par le dossier KYC.

   **Sans preuve rattachée au compte, le support propose de créer un nouveau compte.**

2. Un Ops titulaire de `ops.accounts.change_phone` (groupe Admin) crée la demande de changement. Pour un compte `owner` ou `technician`, un **second Ops** doit l'approuver.
3. Jeflink envoie au nouveau numéro un challenge `change_phone`. L'utilisateur saisit lui-même le code dans l'app (« J'ai changé de numéro »). L'Ops ne voit jamais le code.
4. Le numéro est remplacé. Toutes les sessions sont révoquées. Un SMS d'information part vers l'ancien numéro. `phone_changed_at` est renseigné, et `wallet` bloquera les actions financières pendant 72 h (à reprendre dans sa spec).
5. Un Ops n'agit jamais sur son propre compte ni sur un autre compte ops. Ces cas passent par les commandes de gestion, avec deux Admin.

(En cas de simple perte de SIM, l'opérateur remplace la SIM avec le même numéro, et rien ne change côté Jeflink.)

### Suppression du compte (exigée par les stores Apple et Google)

« Mon compte › Supprimer mon compte » demande un OTP `delete_account`, puis anonymise le compte (voir Données personnelles).

## Réalité terrain

- **Délais SMS.** Un SMS peut arriver après 1 à 3 minutes, et parfois après le renvoi. Chaque code reste valable 10 min, et **tous les codes envoyés pour un même challenge restent valides**.
- **Coupures au pire moment** (T1) :
  - `otp/request` est idempotent ;
  - le challenge est reprenable ;
  - `otp/verify` peut être rejoué pendant 2 min ;
  - le refresh a une fenêtre de grâce.

  Aucune coupure ne coûte un SMS ou une déconnexion.

- **Trois opérateurs** (Orange, Free/Yas, Expresso) : la délivrabilité est mesurée par préfixe opérateur (`+22177`), jamais sur le numéro.
- **CGNAT mobile.** Des milliers d'abonnés partagent la même IP. La limite par IP reste donc large ; les vraies protections sont les limites par numéro et les plafonds.
- **Pro hors ligne pendant des jours.** La durée d'inactivité du refresh est de 60 j, et la file d'actions rafraîchit la session avant de rejouer.
- **Littératie.** Remplissage automatique du code, code en chiffres seuls, SMS court sans sigle, boutons d'au moins 48 px, aide en pictogrammes et en audio.
- **Wolof.** Le wolof est **absent du parcours de connexion V1** : les clés existent, pas le contenu. Il faut produire tôt le texte et l'audio `wo` (Q12).
- **Formats saisis.** `77 123 45 67`, `771234567`, `00221771234567`, `221 77…` et `+221…` sont tous normalisés.
- **Confiance et arnaque.** Le code de connexion ne doit jamais être confondu avec le **code de fin** de mission. Le SMS client dit « ni à un artisan », le SMS Pro « ni à un client ». La spec `bookings` doit prévoir un code de fin visuellement distinct.
- **SMS en GSM-7.** Un caractère hors GSM-7 (ê, ç, î, ô, espace insécable…) fait passer le SMS en UCS-2 (70 caractères, donc 2 SMS facturés). Les gabarits sont testés. Le « ë » du wolof n'est pas en GSM-7 (Q12).
- **Téléphone partagé en famille, changement d'appareil** : purge à la déconnexion, file d'actions liée au compte, écran « Autres appareils » (T2).
- **Numéros recyclés** par les opérateurs (S18, Q18). Aucune règle sénégalaise publique ne fixe le délai de réattribution : ni l'ARTP (pages numérotation et FAQ), ni Orange, ni Yas n'en publient. Référence régionale : au Togo, l'ARTP-Togo tient un numéro pour inactif après 3 mois et autorise sa réattribution 3 mois après désactivation, soit environ 6 mois au total. Au Sénégal, plus de 1,5 million de numéros ont été désactivés en 2025 pour défaut d'identification : un recyclage massif est donc plausible dès aujourd'hui. **La règle « compte dormant » est livrée en V1**, sans attendre un délai qu'on ne connaît pas.
- **Diaspora.** Le modèle accepte tout mobile E.164 valide. **Décision Q1 : en V1, l'OTP n'est envoyé qu'aux numéros du Sénégal** (`OTP_ALLOWED_REGIONS = ["SN"]`). L'écran dédié (T3) oriente Moussa (« un proche à Dakar peut commander pour vous ») ; l'ouverture à la diaspora est une question de configuration, sans code.

## Modèle de données et API

### Domaines touchés

| Domaine                   | Changement                                                                                                                                                                                                                                                   |
| ------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `accounts`                | `User` réécrit. Nouveaux modèles : `RoleGrant`, `RoleInvitation`, `OtpChallenge`, `OtpDelivery`, `OtpPhoneBlock`, `DeviceSession`, `TotpDevice`, `OpsEnrollmentToken`, `MfaChallenge`, `PhoneChangeRequest`. Services, sélecteurs, API, tâches, permissions. |
| `trust` (nouveau)         | `AuditEvent` + service `audit()`, rien d'autre.                                                                                                                                                                                                              |
| `notifications` (nouveau) | Paquet `notifications/sms/` : `SmsGateway` et adaptateur `fake`. Aucun modèle.                                                                                                                                                                               |
| `common`                  | `pii.py` (masquage, HMAC des numéros), filtre de logs, `gsm7.py`, vérifications au démarrage.                                                                                                                                                                |
| `providers` (futur)       | **Frontière seulement.** `providers` appelle `invite_to_role`, `revoke_role` et `register_invitation_handler`. `accounts` n'importe jamais `providers`.                                                                                                      |

### Modèles

**`accounts.User`** : réécrit sur `BaseModel + AbstractBaseUser + PermissionsMixin`, migration `0001_initial` régénérée. `username`, `first_name`, `last_name` et `date_joined` disparaissent.

| Champ                                                                            | Type                      | Règle                                                                                                                                                                  |
| -------------------------------------------------------------------------------- | ------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `public_id`, `created_at`, `updated_at`                                          | via `BaseModel`           | `public_id` = `sub` du JWT.                                                                                                                                            |
| `phone`                                                                          | `CharField(16)`, nullable | E.164, `USERNAME_FIELD`. `UniqueConstraint`, `CheckConstraint` regex `^\+[1-9][0-9]{7,14}$`.                                                                           |
| `phone_verified_at`, `phone_changed_at`                                          | `DateTimeField`           | `phone_changed_at` sert au refroidissement de 72 h côté `wallet`.                                                                                                      |
| `display_name`                                                                   | `CharField(80)`, blank    | 2 à 80 caractères. Pas de caractère de contrôle ni bidi, pas d'URL, pas de terme réservé (« Jeflink », « Support », « Ops »…) (S26). Ce n'est pas l'identité KYC (Q9). |
| `email`                                                                          | `EmailField`, blank       | Informatif : ni unique, ni vérifié, **jamais utilisé pour la récupération** (S27).                                                                                     |
| `preferred_language`                                                             | choix `fr`, `wo`          | Défaut `fr`.                                                                                                                                                           |
| `profile_status`                                                                 | choix `guest`, `complete` | `CheckConstraint` : `complete` implique un `display_name` non vide.                                                                                                    |
| `terms_version`, `terms_accepted_at`                                             |                           | Mis à jour à chaque `verify` si la version présentée est plus récente (S11).                                                                                           |
| `is_active`, `deactivation_reason` (code : `fraud`, `user_request`, `ops_other`) |                           | Un compte désactivé pour `fraud` ne peut être réactivé que par un Ops différent (S30).                                                                                 |
| `is_staff`                                                                       | bool                      | Admin Django de l'équipe technique seulement. `otp/verify` refuse d'ouvrir une session API pour `is_staff` ou `is_superuser` (S3).                                     |
| `is_review_account`                                                              | bool                      | Compte de revue des stores (S17). `grant_role` refusé dessus.                                                                                                          |
| `deleted_at`                                                                     | null                      | `CheckConstraint` : `phone IS NOT NULL OR deleted_at IS NOT NULL`.                                                                                                     |

Autres règles :

- Mot de passe inutilisable, sauf pour les superutilisateurs techniques.
- Permissions Ops propres au domaine, déclarées dans `User.Meta.permissions` : `ops_accounts_view`, `ops_accounts_manage`, `ops_accounts_change_phone`.

**`accounts.RoleGrant`** : `user`, `role` (`owner`, `technician`, `ops`), `granted_by`, `created_at`, `revoked_at`, `revoked_by`, `reason_code`. `UniqueConstraint(user, role)` quand `revoked_at IS NULL`. Le rôle `client` n'est pas stocké : tout compte non supprimé est client.

**`accounts.RoleInvitation`** (S19) :

| Champ                                                                                       | Règle                                                                                         |
| ------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------- |
| `phone` (E.164), `role` (`owner` ou `technician`)                                           | Le numéro est gardé tant que l'invitation n'est pas acceptée, refusée ou expirée, puis purgé. |
| `invited_by` FK, `display_name_hint`, `context_ref` (UUID opaque appartenant à `providers`) |                                                                                               |
| `expires_at` (7 j), `accepted_at`, `accepted_by` FK null, `declined_at`                     |                                                                                               |

**`accounts.OtpChallenge`** :

| Champ                                                                                                                  | Règle                                                         |
| ---------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------- |
| `phone`, `purpose` (`login`, `delete_account`, `change_phone` ; `sensitive_action` réservé à `wallet`), `user` FK null |                                                               |
| `challenge_secret_hash`                                                                                                | Secret de 32 octets remis au client, stocké en SHA-256 (S12). |
| `idempotency_key_hash`                                                                                                 | HMAC de l'`Idempotency-Key` (T1).                             |
| `app` (imposé par le BFF pour `web` et `console`), `language`                                                          |                                                               |
| `status` (`pending`, `verified`, `locked`, `expired`), `failed_attempts`, `expires_at`                                 | `expires_at` vaut au plus création + 30 min (S8).             |
| `verified_at`, `verified_install_id`, `session` FK null                                                                | Servent au rejeu de `verify` pendant 2 min (T1).              |

**`accounts.OtpDelivery`** :

| Champ                                                                                                                   | Règle                                                                              |
| ----------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------- |
| `challenge`, `attempt_no` (1 à 3)                                                                                       | `UniqueConstraint`, `CheckConstraint`.                                             |
| `channel` (`sms` ; `whatsapp` et `voice` réservés)                                                                      |                                                                                    |
| `code_hash`                                                                                                             | HMAC-SHA256(`OTP_HMAC_KEY`, `delivery.public_id` + code). Jamais de code en clair. |
| `expires_at`                                                                                                            | Fixé **à la génération** du code, 10 min (S8).                                     |
| `status` (`queued`, `sent`, `failed`, `unknown`), `gateway`, `provider_message_id`, `segments`, `error_code`, `sent_at` | Sert aussi de compteur de secours si Redis tombe (S8).                             |

**`accounts.OtpPhoneBlock`** : `phone_hmac` (unique), `level`, `blocked_until`. Paliers de blocage de 1 h, 2 h, 4 h… jusqu'à 24 h (S8). Levé par `ops/accounts/{id}/unblock-otp` (S12).

**`accounts.DeviceSession`** (son `public_id` sert de claim `sid`) :

| Champ                                                                                                                                                                           | Règle                                                                                                                              |
| ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------- |
| `user`, `app`, `platform`, `device_label`, `install_id`                                                                                                                         |                                                                                                                                    |
| `refresh_hash` (unique), `current_refresh_used_at`                                                                                                                              | `current_refresh_used_at` est renseigné à la première présentation du refresh courant.                                             |
| `previous_refresh_hash`, `rotated_at`, `grace_used_at`                                                                                                                          | Portent la grâce : une seule par rotation, 24 h au plus (voir Sessions).                                                           |
| `auth_time`, `mfa_verified_at`                                                                                                                                                  | `auth_time` = dernier OTP réussi ; il alimente `RequiresRecentAuth`.                                                               |
| `last_seen_at`, `idle_expires_at`, `absolute_expires_at`                                                                                                                        |                                                                                                                                    |
| `revoked_at`, `revoked_reason` (`logout`, `user_revoked`, `ops_revoked`, `reuse_detected`, `limit`, `phone_changed`, `account_deleted`, `account_disabled`, `ops_role_changed`) | Au plus 10 sessions actives par compte. Au-delà, la plus ancienne est révoquée, avec l'événement `accounts.session.evicted_limit`. |

**`accounts.TotpDevice`** : `user` OneToOne, `secret_encrypted` (MultiFernet, `MFA_ENCRYPTION_KEY`), `confirmed_at`, `last_used_step`, `locked_at`.

**`accounts.OpsEnrollmentToken`** (S1) : `user`, `token_hash`, `issued_by_operator`, `expires_at` (24 h), `used_at`.

**`accounts.MfaChallenge`** (S1) : `user`, `otp_challenge` FK, `token_hash` (32 octets), `app` (toujours `console`), `expires_at` (5 min), `used_at`, `failed_attempts` (5 au plus).

**`accounts.PhoneChangeRequest`** (S2) :

| Champ                                                                                                  | Règle                                                                                |
| ------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------ |
| `user`, `new_phone`, `requested_by`, `approved_by` (null ; différent de `requested_by`)                | Approbation par un second Ops exigée si le compte a un rôle `owner` ou `technician`. |
| `reason_code`, `note` (280 caractères au plus, filtrée), `status`, `expires_at` (24 h), `completed_at` | `new_phone` est purgé une fois la demande close.                                     |

**`trust.AuditEvent`** : en ajout seul. Champs : `public_id`, `created_at`, `actor` (PROTECT), `actor_kind` (`user`, `ops`, `system`), `action`, `target_type`, `target_public_id`, `session_public_id`, `request_id`, `metadata` (JSON). Admin en lecture seule.

- `metadata` est validé contre un **schéma par action** (`AUDIT_METADATA_SCHEMAS`). Un numéro n'y figure que sous forme `mask_phone()` + `phone_hmac` (S15).
- L'audit d'un chemin d'erreur est écrit **hors de la transaction appelante**, pour survivre à son rollback.

### Normalisation et validation du téléphone

- `accounts.services.normalize_phone(raw, default_region="SN") -> str` (`phonenumbers`) renvoie l'E.164 ou lève `phone_invalid`. Espaces, tirets et points sont ignorés ; `00` et `+` sont acceptés ; sans préfixe, la région par défaut est le Sénégal.
- **Type de ligne (T3)** : seul un numéro **sûrement fixe** (`FIXED_LINE`) est rejeté, avec `phone_not_mobile`. `MOBILE`, `FIXED_LINE_OR_MOBILE` et `UNKNOWN` sont acceptés : les métadonnées libphonenumber ont du retard sur les nouvelles plages locales.
- Politique d'envoi : `OTP_ALLOWED_REGIONS` (défaut `["SN"]`). Hors liste : `400 phone_region_not_supported`, qui mène à l'écran dédié. On compte par région, sans le numéro.
- `phone_display` : format national pour +221, international sinon.
- Les erreurs ne renvoient jamais la saisie brute (S14).

### OTP

**Limites de débit** (réglages ; compteurs Redis atomiques `INCR+EXPIRE` en script Lua, clés en HMAC avec `PII_HMAC_KEY`, **évalués avant toute écriture**) :

| Axe                                                                                                      | Limite                                                                                                                  | Au-delà                                                                                                                                     |
| -------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------- |
| Numéro : SMS envoyés, **tous motifs** (connexion, renvoi, suppression, changement de numéro, invitation) | 5/h et 8/24 h                                                                                                           | `429 otp_rate_limited` + `retry_after`                                                                                                      |
| Numéro : échecs de vérification                                                                          | 10 sur 24 h glissantes                                                                                                  | Nouveaux challenges bloqués 1 h, puis 2 h, 4 h… jusqu'à 24 h (`OtpPhoneBlock`). Les **sessions existantes restent intactes**. `AuditEvent`. |
| Challenge                                                                                                | 5 essais (puis `locked`), 3 envois, 60 s entre deux envois, 30 min de vie au plus                                       | `otp_locked`, `otp_resend_exhausted`, `otp_resend_too_early`                                                                                |
| Code                                                                                                     | 10 min après sa génération                                                                                              | `otp_expired`                                                                                                                               |
| IP (CGNAT, donc large)                                                                                   | `request` 30/10 min ; `verify` 60/10 min ; `token/refresh` 60/min ; `phone-change/confirm` 20/10 min ; `config` 120/min | `429`                                                                                                                                       |
| `install_id` (mobile, signal faible)                                                                     | 10 `request`/h                                                                                                          | `429`                                                                                                                                       |
| Préfixe opérateur (5 chiffres) et bloc de 1 000 numéros                                                  | Plafonds horaires (réglages)                                                                                            | `429`, puis alerte                                                                                                                          |
| Invitations (S19)                                                                                        | 20/jour/pro, et comptées dans les limites « numéro »                                                                    | `429 invitation_rate_limited`                                                                                                               |
| `mfa_token` / compte ops                                                                                 | 5 essais par jeton ; 10 échecs TOTP/24 h                                                                                | Verrou console jusqu'à `reset_ops_mfa`, `accounts.mfa.locked`, alerte                                                                       |
| Global quotidien (`SMS_DAILY_CAP`, total et par région)                                                  | Alertes à 50 % et 80 %                                                                                                  | `503 otp_temporarily_unavailable` **au plafond dur seulement**, `system.sms_cap.reached`                                                    |
| Taux de conversion (vérifiés/envoyés, 1 h glissante)                                                     | Moins de 20 %                                                                                                           | Ralentissement (délai de renvoi doublé, plafonds de préfixe divisés par 2) + alerte                                                         |

Si Redis ne répond pas, `reserve_sms` compte en base à partir de `OtpDelivery` (numéro, total du jour, région). À défaut, l'API répond `503 otp_temporarily_unavailable`. On ne tombe **jamais en mode ouvert** (S8). Conséquence assumée (revue sécurité du 2026-09-30) : la limite par IP de `otp/request` refuse elle aussi quand Redis tombe, donc **une panne Redis coupe les nouvelles connexions OTP** ; les sessions ouvertes continuent. Chaque vue `AllowAny` déclare sa limite et garde `IpRateThrottle`, un test le vérifie (S29). Les IPv6 sont comptées par /64.

**Demande (`otp/request`) :**

- Crée **toujours un nouveau challenge** et un `challenge_secret` (S12). La réponse ne dépend ni des challenges existants ni de l'existence du compte.
- Rejouer la même `Idempotency-Key` avant `resend_available_at` renvoie `202` avec **le même corps** (même `challenge_id`, même `challenge_secret`), sans SMS (T1). La réponse est gardée dans Redis, chiffrée, jusqu'à `resend_available_at`, sous une clé HMAC(clé d'idempotence + numéro).

**Renvoi** : `otp/resend` avec `{challenge_id, challenge_secret}`.

**Anti-énumération.** Connexion et inscription forment un seul parcours. `request` répond `202` avec la même forme dans tous les cas. Le compte n'est créé qu'**après** la vérification. `account_disabled` n'apparaît qu'une fois le code validé.

Risque résiduel documenté : un tiers peut déclencher le blocage d'un numéro par des échecs répétés. Le blocage n'affecte pas les sessions existantes, et l'Ops peut le lever avec `unblock-otp`, action auditée.

**Vérification (`otp/verify`).** Ordre des contrôles fixé et testé (S11) :

1. format ;
2. challenge : existe, `challenge_secret` valide, `purpose = login` (S16), non expiré, non verrouillé ;
3. code : `compare_digest` sur tous les codes non expirés du challenge, **sans sortie anticipée** ;
4. état du compte : actif, ni `is_staff` ni `is_superuser` ;
5. création éventuelle ; `terms_version` est **obligatoire pour tous**.

Les échecs incrémentent `failed_attempts`, et la validation passe par un `UPDATE` conditionnel qui doit toucher **exactement une ligne** (S8). Un test lance 20 vérifications concurrentes.

**Rejeu de `verify` (T1).** Dans les 2 min suivant un succès, le même code, le même `challenge_secret` et le même `install_id` rendent de nouveaux jetons pour la **même** `DeviceSession`, avec rotation. Toute autre combinaison renvoie `otp_already_used`, jamais `otp_invalid`.

**Envoi (tâche `accounts.tasks.send_otp(delivery_public_id)`, ADR 0008).**

- Le code est généré **dans le worker** et ne transite jamais par le broker.
- Idempotence : la tâche sort si `status = sent`.
- `SmsTransientError` : nouvel essai, avec un nouveau code.
- `SmsAmbiguousError` : pas de nouvel essai, `status = unknown`.
- `SmsPermanentError` : `status = failed`.

**Gabarits SMS** : GSM-7, au plus 160 caractères, **aucune donnée utilisateur** (S13). Deux gabarits distincts, client et Pro, en msgid testés :

```
Jeflink : votre code de connexion est 482913. Valable 10 min. Ne le donnez à personne, ni à un artisan, ni à Jeflink.
<hash Android de l'app client>
@jeflink.sn #482913
```

```
Jeflink Pro : votre code de connexion est 482913. Valable 10 min. Ne le donnez à personne, ni à un client, ni à Jeflink.
<hash Android de l'app Pro>
@jeflink.sn #482913
```

- `SMS_ANDROID_APP_HASH` est **obligatoire**, avec un hachage par app et par clé de signature (debug, release, Play App Signing).
- La dernière ligne suit le format WebOTP. Le domaine est à confirmer.
- Gabarits dédiés et courts pour `change_phone`, `delete_account`, l'invitation et l'information à l'ancien numéro.
- `wo` : plus tard, avec repli sur `fr` (Q12).

**SmsGateway (ADR 0008)** : `jeflink/notifications/sms/`.

- `base.py` : `send(*, to, body, idempotency_key, sender_id) -> SmsResult`, et trois exceptions.
- `fake.py` : autorisé, avec affichage du code en console, **seulement si `DJANGO_ENV ∈ {local, test}`**, jamais selon `DEBUG` (S23).
- Les adaptateurs ne journalisent jamais les corps HTTP (S14).

Fournisseur à choisir (Q7). Pistes : Orange (API SMS), Infobip, Twilio, Vonage, Africa's Talking (couverture du Sénégal à vérifier), agrégateurs locaux. Critères :

- prix local et international ;
- délivrabilité par opérateur et délai médian ;
- enregistrement de l'expéditeur « JEFLINK » (opérateurs, ARTP) ;
- accusés de réception (DLR) ;
- appel vocal en option ;
- **lieu de traitement et contrat de sous-traitance (DPA)** pour la CDP (S22).

**Défi client (S13).** Le drapeau `OTP_CHALLENGE_REQUIRED` est livré en V1, **désactivé**. Activé, il exige sur `otp/request` un jeton Play Integrity, App Attest ou Turnstile (web). Il est annoncé par `GET /api/auth/config/`.

**Compte de revue des stores (S17)** :

- SIM détenue par Jeflink, `is_review_account = true`, créé par une commande auditée ;
- code aléatoire, changé à chaque soumission, comparé en temps constant ;
- actif seulement jusqu'à `OTP_REVIEW_ENABLED_UNTIL` et pour `app ∈ {client, pro}` ;
- l'API refuse de démarrer si un numéro de `OTP_REVIEW_ACCOUNTS` correspond à un compte non marqué ;
- ses données ne sont jamais diffusées aux vrais pros ;
- chaque usage écrit un `AuditEvent` et déclenche une alerte.

### Sessions et jetons (ADR 0007)

- **Access JWT** : simplejwt, HS256, clé choisie par `kid` parmi 2 clés en rotation (`JWT_SIGNING_KEY`).
  - Claims : `iss`, `aud`, `sub`, `sid`, `auth_time`, `mfa` (bool), `mfa_at`, `iat`, `exp`, `jti`.
  - Aucun rôle dans le jeton : les rôles sont relus en base.
- **Refresh** : jeton opaque de 32 octets, préfixé `jfr_`, stocké en SHA-256 dans `DeviceSession`. Rotation à chaque usage.
- **Grâce (arbitrage T1 × S6, Q15)**. Sous `select_for_update`, l'**ancien** refresh est accepté **une seule fois par rotation**, et seulement :
  - si le refresh courant n'a jamais été présenté (`current_refresh_used_at` nul) ;
  - si la rotation date de **moins de 24 h** ;
  - si la grâce n'a pas déjà servi (`grace_used_at` nul).

  L'usage de grâce ne modifie ni `previous_refresh_hash` ni `rotated_at`. Il renvoie un nouvel access et **le refresh courant**, sans nouvelle rotation. **Toute autre présentation d'un ancien refresh est une réutilisation** : la session est révoquée et `accounts.session.refresh_reuse_detected` est écrit.

- **Authentification** `SessionJWTAuthentication` : elle valide le JWT (`kid`), charge l'utilisateur, refuse un compte inactif ou supprimé, et vérifie que la session est **active** (S7).
  - Cache Redis `auth:sid:<sid>` (TTL 60 s), repli sur la base.
  - La clé est écrite en `on_commit` et supprimée à la révocation.
  - La déconnexion d'un appareil perdu prend effet au plus tard 60 s après, et immédiatement sur l'instance qui révoque.
- **Redis de production** : authentification, TLS si le réseau n'est pas privé, **aucune éviction** des clés d'auth et de limites (base dédiée en `noeviction`) (S7).
- `DEFAULT_AUTHENTICATION_CLASSES = [SessionJWTAuthentication]`. `SessionAuthentication` sort de l'API.
- **Réauthentification récente** : `RequiresRecentAuth(max_age)` s'appuie sur `auth_time` (S18) ; `wallet` s'en servira.
- **Compte dormant (S18, Q17 = 60 j, V1).** Si un `otp/verify` vise un compte sans activité depuis **plus de 60 j** (aucune `DeviceSession` du compte vue depuis 60 j ; une session purgée compte comme inactive) depuis un `install_id` absent des sessions conservées du compte, la session ouverte est **restreinte** (claim `restricted = true`, relu en base). Une session restreinte n'accède ni à l'historique, ni aux adresses, ni aux conversations, ni au portefeuille. Ce qu'on propose ensuite :
  - **client** : écran « Ce numéro a peut-être changé de propriétaire » avec deux choix. [Repartir de zéro] anonymise l'ancien compte (`register_anonymizer`) et en crée un nouveau sur le numéro ; c'est l'option par défaut. [C'est bien mon compte] mène au support WhatsApp, et l'Ops lève la restriction après vérification (réservations récentes décrites ; action auditée `accounts.dormant.cleared`) ;
  - **owner / technician** : restriction jusqu'à revue Ops (correspondance KYC dès que `trust` le permet), avec le message « Votre compte est en vérification » et le lien support ;
  - **ops** : sans objet, la session console exige le TOTP.

  Le compromis est assumé : une vraie cliente revenue après plus de 60 j sur un nouveau téléphone passe par cet écran. Elle garde toujours une issue humaine (T3).

| Contexte (`app`)                | Access | Refresh : inactivité | Refresh : absolu | Autre                                            |
| ------------------------------- | ------ | -------------------- | ---------------- | ------------------------------------------------ |
| `client`, `pro` (mobile)        | 15 min | 60 j                 | 180 j            |                                                  |
| `web` (client)                  | 15 min | 30 j                 | 90 j             |                                                  |
| `console`, compte sans rôle ops | 15 min | 30 j                 | 90 j             |                                                  |
| `console`, compte ops           | 10 min | **30 min**           | 12 h             | TOTP de moins de 5 min pour `ops_*_manage` (S25) |

- **Refresh sur la console** : il recalcule le claim `mfa`. Un TOTP réinitialisé ou verrouillé, ou un rôle ops retiré, donne `mfa = false`. `reset_ops_mfa` et `revoke_ops_role` révoquent les sessions console (S1).
- **Mobile** (S20) :
  - refresh dans `expo-secure-store` avec `keychainAccessible = WHEN_UNLOCKED_THIS_DEVICE_ONLY` ; access en mémoire ;
  - Android : `allowBackup = false`, ou règles d'exclusion couvrant la session et les caches ;
  - sur un 401, un seul refresh à la fois.
- **Déconnexion** : `POST /api/auth/logout/` révoque la session, puis le client purge ses données (T2).

### BFF Next (web et console)

- **Cookies.** Le navigateur ne voit **jamais** un jeton.
  - `__Host-jf_at` : access (`HttpOnly`, `Secure`, `SameSite=Lax`, `Path=/`).
  - `__Secure-jf_rt` : refresh (`HttpOnly`, `Secure`, `SameSite=Strict`, `Path=/api/auth`, **jamais élargi**).
  - `__Host-jf_mfa` : `mfa_token` (`HttpOnly`, `SameSite=Strict`, 300 s) (S10).
  - `__Host-jf_dev` : identifiant d'appareil web, qui tient lieu d'`install_id`.
- **Refresh web** : il n'a lieu **que** dans le route handler `/api/auth/token/refresh`. Les Server Components et le middleware ne rafraîchissent jamais : ils redirigent vers `/api/auth/token/refresh?next=<chemin validé>`. Un verrou entre onglets (`navigator.locks`, repli `BroadcastChannel`) évite deux refresh concurrents (S6).
- **`app` imposé** par le BFF (`web` ou `console`). Aucune permission ne dépend de `app` (S10).
- **Aucun état de module côté serveur (S4)** : jeton, promesse de refresh et en-têtes sont propres à chaque requête. Un test envoie 2 requêtes concurrentes de comptes différents.
- **Cache (S4)** :
  - données authentifiées en `cache: "no-store"` et `dynamic = "force-dynamic"` ;
  - `unstable_cache`, `use cache` et `cache()` interdits sans clé `sub` ;
  - réponses en `Cache-Control: private, no-store` avec `Vary: Cookie, Authorization` ;
  - le CDN ne met jamais `/api/*` en cache.
- **Proxy générique `app/api/[...path]` (S9)** :
  - chemin normalisé sous `/api/` ; refus de `..`, `%2e`, `%2f`, `\` et des URL absolues ;
  - refus de `/api/internal/`, `/api/webhooks/` et `/api/schema/` ;
  - **liste fermée** d'en-têtes transmis ; retrait des `Authorization`, `Cookie`, `X-Forwarded-*` et `X-Jeflink-*` venus du navigateur, et des `Set-Cookie` venus de Django ;
  - JSON imposé hors GET.
- **CSRF** :
  - contrôle `Origin` sur toute méthode non GET, **y compris `/api/auth/*`**, contre des origines exactes par app ;
  - en-tête `X-Requested-With: jeflink` exigé.

  Django n'accepte que le Bearer : ni CSRF ni CORS côté API.

- **IP cliente (S9)** : le BFF envoie l'en-tête dédié `X-Jeflink-Client-Ip`, lu depuis une source fiable unique et jamais recopié depuis `X-Forwarded-For`, accompagné de `X-Jeflink-Bff: <secret>`. `TrustedClientIpMiddleware` n'y croit que si **les deux conditions** sont réunies :
  - le secret est valide (`compare_digest`, 2 secrets acceptés pour la rotation) ;
  - la requête arrive par l'hôte interne.

  Pour le mobile, `REMOTE_ADDR` est réglé par le reverse proxy.

- **Secrets** : jamais en `NEXT_PUBLIC_`. Un test de build parcourt `.next/static` à leur recherche (S9).
- **En-têtes** : CSP stricte sur la console ; `Referrer-Policy: no-referrer` sur `/connexion` (S10). Le paramètre `next` doit être un chemin relatif interne validé (S20).
- **Client API** : `configureApiClient()` est un singleton, donc côté serveur, le jeton passe **par appel**. Les aides serveur vivent dans `packages/api-client/src/bff/` (`server-only`), seul second `fetch` autorisé (ADR 0007 amende ADR 0006). `jeflinkFetch` gagne un `Authorization` par appel prioritaire, `onUnauthorized` (un seul refresh à la fois, un rejeu) et l'en-tête `X-Requested-With`.

### Rôles et permissions

- `client` est implicite. `owner`, `technician` et `ops` sont des `RoleGrant` actifs. Les rôles se cumulent.
- `owner` et `technician` naissent d'une **invitation acceptée** (`RoleInvitation`) ou d'un service de `providers` (inscription pro). `providers` enregistre `register_invitation_handler(role, fn)` pour créer l'appartenance à l'équipe au moment de l'acceptation.
- `ops` naît **uniquement** de `manage.py grant_ops_role (--user <public_id> | --phone) --groups --operator --second-operator --reason`, qui émettra aussi le jeton d'enrôlement TOTP (tâche 13). Les deux opérateurs sont des **Admin actifs désignés par `public_id`**, distincts entre eux et de la cible ; le motif est énuméré. Seule exception : `--bootstrap` crée le premier Admin tant qu'il n'en existe aucun. Chaque changement de groupe écrit `accounts.ops_groups.changed` (S1, S3).
- Classes DRF (`jeflink/accounts/permissions.py`, S5) :

| Classe                                 | Vérifie                                                                                                                                                                                                                                                                                                            |
| -------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `IsClient`                             | Authentifié, actif, non supprimé                                                                                                                                                                                                                                                                                   |
| `RequiresCompleteProfile`              | `profile_status = complete`, sinon `403 profile_incomplete`                                                                                                                                                                                                                                                        |
| `RequiresRecentAuth(max_age)`          | `auth_time` plus récent que `max_age`, sinon `403 reauth_required`                                                                                                                                                                                                                                                 |
| `HasOwnerRole`                         | `RoleGrant owner` actif                                                                                                                                                                                                                                                                                            |
| `HasTechnicianRole`                    | `RoleGrant technician` ou `owner` actif (l'artisan solo est son propre technicien, ADR 0003)                                                                                                                                                                                                                       |
| `HasOpsPerm("ops.<domaine>.<action>")` | `RoleGrant ops` actif, claim `mfa = true`, permission Django `<domaine>.ops_<action>` via un groupe. Avec `step_up=True` (paramètre **explicite** à chaque usage, jamais déduit du nom de l'action), `mfa_at` de moins de 5 min, sinon `403 ops_step_up_required`. **Ne s'appuie jamais sur `is_superuser`** (S3). |

- `IsProOwner` et `IsTechnicianAssigned` sont **réservés** aux classes objet de `providers` et `bookings`. D'ici là, ils existent comme classes qui **refusent par défaut**.
- Les listes sont toujours filtrées par un sélecteur qui prend `user`. Un test « refusé » porte sur l'objet d'un autre utilisateur et attend un 404.
- Les profils Ops (« Support », « Validation KYC », « Finance », « Admin ») sont des `Group` créés par migration de données. `ops_accounts_change_phone` est accordé au seul groupe Admin.

### Endpoints

Tags OpenAPI : `auth`, `me`, `ops-accounts`. **Aucune donnée personnelle dans les URL** (S14). Toutes les listes sont paginées par curseur.

| Méthode     | Chemin                                                       | Permission                                                                   | Réponse / notes                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                       |
| ----------- | ------------------------------------------------------------ | ---------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| GET         | `/api/auth/config/`                                          | AllowAny + limite                                                            | `{regions[{region, dial_code, label}], code_length, client_challenge_required}`                                                                                                                                                                                                                                                                                                                                                                                                                                                                       |
| POST        | `/api/auth/otp/request/`                                     | AllowAny + limites [sécu]                                                    | En-tête `Idempotency-Key` obligatoire. Corps `{phone, app (mobile), client_challenge_token?}` → `202 {challenge_id, challenge_secret, phone_display, code_length, expires_at, resend_available_at, deliveries_remaining}`. Erreurs : `phone_invalid`, `phone_not_mobile`, `phone_region_not_supported`, `otp_rate_limited`, `otp_temporarily_unavailable`, `client_challenge_failed`.                                                                                                                                                                 |
| POST        | `/api/auth/otp/resend/`                                      | AllowAny + limites [sécu]                                                    | `{challenge_id, challenge_secret}` → `202`, même forme sans secret. Erreurs : `otp_resend_too_early`, `otp_resend_exhausted`, `otp_challenge_invalid`.                                                                                                                                                                                                                                                                                                                                                                                                |
| POST        | `/api/auth/otp/verify/`                                      | AllowAny + limites [sécu]                                                    | `{challenge_id, challenge_secret, code, terms_version, device{platform, label?, install_id}}`. Réponse selon `status` : `authenticated` → `{user, is_new_user, other_sessions[{public_id, device_label, last_seen_at}], pending_invitations[], tokens}` ; `mfa_required` ou `mfa_enrollment_required` → `{mfa_token}` (cookie `__Host-jf_mfa` côté BFF). Erreurs : `otp_invalid` (+ `attempts_remaining`), `otp_expired`, `otp_locked`, `otp_already_used`, `otp_challenge_invalid`, `terms_not_accepted`, `account_disabled`, `account_not_allowed`. |
| POST        | `/api/auth/token/refresh/`                                   | AllowAny + limite [sécu]                                                     | `{refresh}` → `{access, refresh, access_expires_at}`. Erreurs : `refresh_invalid`, `session_revoked`.                                                                                                                                                                                                                                                                                                                                                                                                                                                 |
| POST        | `/api/auth/logout/`                                          | Authentifié                                                                  | `204`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 |
| POST        | `/api/auth/mfa/totp/setup/`                                  | `mfa_token` + `{enrollment_token}` [sécu]                                    | `{secret, otpauth_uri}`. Refusé si un `TotpDevice` confirmé existe. Erreur : `mfa_enrollment_not_authorized`.                                                                                                                                                                                                                                                                                                                                                                                                                                         |
| POST        | `/api/auth/mfa/totp/confirm/`                                | `mfa_token` [sécu]                                                           | `{code}` → `authenticated`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            |
| POST        | `/api/auth/mfa/totp/verify/`                                 | `mfa_token` [sécu]                                                           | `{code}` → `authenticated`. Erreurs : `mfa_invalid`, `mfa_token_invalid`, `mfa_locked`.                                                                                                                                                                                                                                                                                                                                                                                                                                                               |
| POST        | `/api/auth/mfa/totp/step-up/`                                | Authentifié, ops, console [sécu]                                             | `{code}` → nouvel access avec `mfa_at` à jour                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         |
| POST        | `/api/auth/phone-change/confirm/`                            | AllowAny + limites [sécu]                                                    | `{phone, code, terms_version, device}` → `authenticated`. Seul un challenge `change_phone` en attente pour ce numéro est accepté.                                                                                                                                                                                                                                                                                                                                                                                                                     |
| GET / PATCH | `/api/me/`                                                   | `IsClient`                                                                   | GET : `{public_id, phone, phone_display, display_name, email, preferred_language, profile_status, roles[], created_at}`. PATCH : `display_name`, `email`, `preferred_language`.                                                                                                                                                                                                                                                                                                                                                                       |
| GET         | `/api/me/sessions/`                                          | `IsClient`                                                                   | `[{public_id, app, platform, device_label, last_seen_at, created_at, is_current}]`                                                                                                                                                                                                                                                                                                                                                                                                                                                                    |
| DELETE      | `/api/me/sessions/{public_id}/`                              | `IsClient` + propriétaire [sécu]                                             | `204` ; session d'un autre utilisateur → 404                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                          |
| POST        | `/api/me/sessions/revoke-others/`                            | `IsClient` [sécu]                                                            | `204`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 |
| GET         | `/api/me/invitations/`                                       | `IsClient`                                                                   | Invitations en attente pour le numéro du compte                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                       |
| POST        | `/api/me/invitations/{public_id}/accept/`, `…/decline/`      | `IsClient` [sécu]                                                            | `204`. `accept` exige `profile_status = complete`, ou un `display_name_hint` qui complète le profil.                                                                                                                                                                                                                                                                                                                                                                                                                                                  |
| POST        | `/api/me/deletion/otp/`                                      | `IsClient` [sécu]                                                            | `202`, forme de `otp/request` (challenge `delete_account` vers le numéro du compte)                                                                                                                                                                                                                                                                                                                                                                                                                                                                   |
| POST        | `/api/me/deletion/`                                          | `IsClient` [sécu]                                                            | `{challenge_id, challenge_secret, code}` → `204`. Exige `purpose = delete_account`, `challenge.user` égal à l'utilisateur courant, et le même numéro (S16). Erreur : `409 account_deletion_blocked`.                                                                                                                                                                                                                                                                                                                                                  |
| POST        | `/api/ops/accounts/search/`                                  | `HasOpsPerm("ops.accounts.view")`                                            | `{phone}` → 0 ou 1 résultat. Audit `ops.accounts.searched`.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                           |
| GET         | `/api/ops/accounts/{public_id}/`                             | `HasOpsPerm("ops.accounts.view")`                                            | Statut, rôles, sessions actives, blocage OTP, dates. Téléphone masqué.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                |
| POST        | `/api/ops/accounts/{public_id}/reveal-phone/`                | `HasOpsPerm("ops.accounts.view")` [sécu]                                     | `{reason_code, note?}` → numéro complet. Audit `ops.accounts.phone_revealed`.                                                                                                                                                                                                                                                                                                                                                                                                                                                                         |
| POST        | `/api/ops/accounts/{public_id}/revoke-sessions/`             | `HasOpsPerm("ops.accounts.manage")` [sécu]                                   | `{reason_code, note?}`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                |
| POST        | `/api/ops/accounts/{public_id}/unblock-otp/`                 | `HasOpsPerm("ops.accounts.manage")` [sécu]                                   | `{reason_code, note?}`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                |
| POST        | `/api/ops/accounts/{public_id}/deactivate/`, `…/reactivate/` | `HasOpsPerm("ops.accounts.manage")` [sécu]                                   | `{reason_code, note?}`. Réactivation après `fraud` : Ops différent de celui qui a désactivé (S30).                                                                                                                                                                                                                                                                                                                                                                                                                                                    |
| POST        | `/api/ops/accounts/{public_id}/phone-change/`                | `HasOpsPerm("ops.accounts.change_phone")` [sécu]                             | `{new_phone, reason_code, note?}` → `PhoneChangeRequest`. Erreurs : `phone_in_use`, `ops_target_forbidden`.                                                                                                                                                                                                                                                                                                                                                                                                                                           |
| POST        | `/api/ops/phone-changes/{public_id}/approve/`, `…/reject/`   | `HasOpsPerm("ops.accounts.change_phone")`, Ops différent du demandeur [sécu] | L'approbation déclenche le challenge `change_phone`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                   |

Règles communes aux endpoints `ops-accounts` :

- **cible interdite** : son propre compte, ou un compte ops (`403 ops_target_forbidden`) ;
- les motifs sont un **code énuméré** plus une note de 280 caractères au plus, filtrée (S14).

Commandes de gestion : `grant_ops_role`, `revoke_ops_role`, `reset_ops_mfa`, `create_review_account`. Chacune exige `--operator` et `--reason`. Sur un compte ops, elle exige aussi `--second-operator` : deux Admin différents. Chacune écrit un `AuditEvent` (S3).

### Tâches Celery

| Tâche                                                                                                | Idempotence                                                              | Planification                                 |
| ---------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------ | --------------------------------------------- |
| `accounts.tasks.send_otp(delivery_public_id)`                                                        | Sort si `status = sent` ; nouvel essai sur `SmsTransientError` seulement | À la demande (en `on_commit`)                 |
| `accounts.tasks.send_notice_sms(kind, target_public_id)` (invitation, information à l'ancien numéro) | Clé d'idempotence par événement                                          | À la demande                                  |
| `accounts.tasks.purge_auth_data()`                                                                   | Suppression par lots, relançable                                         | Quotidienne (`CELERY_BEAT_SCHEDULE` statique) |

En test, `send_otp.apply_async` et `delay` sont interceptés (Celery en mode EAGER) pour vérifier que le code ne figure dans aucun argument (S28).

### Données personnelles et AuditEvent

- **Filtre de logs (S14)**, appliqué à Django **et** au BFF. Il masque :
  - les numéros E.164 ;
  - les formats nationaux, motif `(?:00221|\+?221)?\s*7[05-8](?:[\s.-]?\d){7}` ;
  - les clés sensibles : `phone`, `new_phone`, `code`, `refresh`, `access`, `mfa_token`, `challenge_secret`, `secret`, `otpauth_uri`, `enrollment_token`, `Authorization`, `Cookie`.

  Sentry : `send_default_pii=False`, aucun corps de requête envoyé sur `auth`, `me` et `ops`, `before_send` filtré.

- **Minimisation.** L'IP n'est jamais stockée en base, sauf décision contraire sur la trace optionnelle (S31, Q16). « Me prévenir » ne stocke aucun numéro.
- **Rétention proposée, à valider par le consultant juridique de Jeflink** (Q8) :

| Donnée                        | Durée                                 |
| ----------------------------- | ------------------------------------- |
| `OtpChallenge`, `OtpDelivery` | 7 j                                   |
| `RoleInvitation` close        | 30 j                                  |
| `PhoneChangeRequest` close    | 30 j (`new_phone` purgé à la clôture) |
| `DeviceSession` révoquée      | 90 j                                  |
| `AuditEvent`                  | 5 ans                                 |

Un registre des traitements documente finalités et durées. La déclaration CDP est faite avant la production, avec la formalité de transfert hors Sénégal si le fournisseur SMS ou l'hébergeur est étranger (S22).

- **Suppression du compte (S16)** : anonymisation, la ligne est conservée.
  - `phone = NULL` ; `display_name` et `email` vidés ; `device_label` et `install_id` effacés ; `is_active = False` ; `deleted_at` renseigné.
  - Sessions et rôles révoqués ; `TotpDevice` supprimé ; `OtpChallenge`, `OtpDelivery` et `RoleInvitation` du numéro supprimés ; jetons push supprimés.
  - Le numéro redevient libre.
  - **`register_anonymizer()` est obligatoire** pour chaque domaine futur qui stocke des données personnelles : c'est un critère « done » des specs suivantes.
  - `register_deletion_blocker()` (vide ici) permettra à `bookings` et `wallet` de refuser la suppression. Un refus écrit `accounts.deletion.blocked`.
  - La rotation des sauvegardes (délai d'effacement effectif) est documentée.
- **`AuditEvent`, actions** (chacune avec son schéma de `metadata`) :

| Famille                  | Actions                                                                                                                                                                                                                |
| ------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Compte                   | `accounts.user.created`, `accounts.otp.verified`, `accounts.otp.locked`, `accounts.otp.phone_blocked`                                                                                                                  |
| Sessions                 | `accounts.session.refresh_reuse_detected`, `accounts.session.revoked`, `accounts.session.evicted_limit`                                                                                                                |
| Rôles et invitations     | `accounts.role.granted`, `accounts.role.revoked`, `accounts.invitation.accepted`                                                                                                                                       |
| Second facteur           | `accounts.mfa.enrolled`, `accounts.mfa.failed`, `accounts.mfa.locked`, `accounts.mfa.reset`                                                                                                                            |
| Numéro et état du compte | `accounts.phone_change.requested`, `accounts.phone_change.approved`, `accounts.phone_change.completed`, `accounts.user.deactivated`, `accounts.user.reactivated`, `accounts.user.deleted`, `accounts.deletion.blocked` |
| Revue des stores         | `accounts.review_account.used`                                                                                                                                                                                         |
| Ops                      | `ops.accounts.searched`, `ops.accounts.phone_revealed`, `ops.accounts.otp_unblocked`                                                                                                                                   |
| Système                  | `system.sms_cap.reached`                                                                                                                                                                                               |

Les demandes d'OTP sont comptées en métriques, sans audit.

### Réglages, dépendances et vérifications au démarrage

- **Dépendances Python** : `djangorestframework-simplejwt`, `phonenumbers`, `pyotp` ; `cryptography` est déjà tiré par simplejwt.
- **Dépendances Expo** :
  - `expo-secure-store` ;
  - `expo-local-authentication` (retenu, Q19 ; dépendance à justifier dans la PR).
- **Réglages** :
  - environnement : `DJANGO_ENV` ;
  - clés (noms réels des variables) : `JWT_SIGNING_KEYS` (`kid:clé`, 2 en rotation, la première active), `OTP_HMAC_KEY`, `MFA_ENCRYPTION_KEYS` (MultiFernet), `BFF_SHARED_SECRETS` (2 valeurs), `PII_HMAC_KEY` (pseudonymisation des numéros et IP : compteurs, `OtpPhoneBlock`, `phone_hmac` d’audit) ;
  - SMS : `SMS_GATEWAY`, `SMS_SENDER_ID`, `SMS_DAILY_CAP` et paliers, `SMS_ANDROID_APP_HASH` (par app) ;
  - OTP : `OTP_ALLOWED_REGIONS`, `OTP_CHALLENGE_REQUIRED` ;
  - revue des stores : `OTP_REVIEW_ACCOUNTS`, `OTP_REVIEW_ENABLED_UNTIL` ;
  - durées de session par `app`.
- **Check Django au démarrage (S21)** : les 5 clés sont présentes, font au moins 32 octets et sont **distinctes entre elles et de `SECRET_KEY`**. `fake` n'est accepté que hors production. La cohérence des comptes de revue est vérifiée.
- **Redis** : `CACHES` sur Redis. Aujourd'hui, le cache LocMem par défaut rend les limites inopérantes entre workers.
- **Exposition** :
  - `/api/schema/` n'est servi qu'en `local`/`test` ou sur l'hôte interne (S24) ;
  - admin Django sur l'hôte interne seulement en production, avec second facteur, en **lecture seule** pour `User`, `RoleGrant`, `DeviceSession`, `TotpDevice`, `OtpChallenge`, `OtpDelivery`, `AuditEvent` et `Group` (S3).
- **Dépôt (S21)** : `.gitignore` ignore déjà `.env*` sauf `.env.example`. gitleaks en pre-commit et en CI.

### Transitions de réservation touchées

Aucune.

## IA (si applicable)

Non applicable. La future détection de faux comptes (IA6, V2) consommera `AuditEvent` et les métriques d'OTP.

## Points de sécurité

Issus de la revue `security-reviewer`. Chaque ligne renvoie à la section où la règle est intégrée.

- **S1** Enrôlement TOTP par jeton hors bande, `mfa_token` haché à usage unique, verrou après 10 échecs, anti-rejeu, révocation des sessions console → Parcours Ops, Modèles (`OpsEnrollmentToken`, `MfaChallenge`), Sessions, Endpoints.
- **S2** Changement de numéro en deux temps, second Ops, procédure écrite, SMS à l'ancien numéro, 72 h de refroidissement, pas d'action sur soi ni sur un ops → Parcours « Numéro perdu », `PhoneChangeRequest`, Endpoints.
- **S3** Admin interne et en lecture seule, pas de session API pour staff et superuser, `HasOpsPerm` sans `is_superuser`, commandes auditées → Réglages, `User`, Rôles, Endpoints.
- **S4** BFF sans état de module, pas de cache sur les données authentifiées, en-têtes `no-store`/`Vary`, CDN hors `/api/*` → BFF.
- **S5** Classes `HasOwnerRole`/`HasTechnicianRole`, classes objet refusant par défaut, listes filtrées par `user`, 404 sur l'objet d'autrui → Rôles et permissions.
- **S6** Grâce du refresh une fois par rotation (24 h, Q15), refresh web limité au route handler, cookie `Path=/api/auth`, verrou entre onglets → Sessions, BFF.
- **S7** Cache Redis des sessions actives (60 s, `on_commit`), Redis de production authentifié, en TLS et sans éviction → Sessions.
- **S8** Compteurs atomiques avant écriture, repli en base puis `503`, `UPDATE` conditionnel, `compare_digest`, expirations fixes, blocage progressif → OTP.
- **S9** IP via `X-Jeflink-Client-Ip` + secret + hôte interne, proxy durci, `Origin` exact, secrets hors `NEXT_PUBLIC_` → BFF.
- **S10** `mfa_token` en cookie `__Host-`, `app` imposé par le BFF, CSP console, `Referrer-Policy` → BFF.
- **S11** `terms_version` obligatoire, ordre des contrôles fixé et testé → OTP (vérification), `User`.
- **S12** Nouveau challenge à chaque demande, `challenge_secret`, endpoint `resend`, risque résiduel et `unblock-otp` → OTP, Endpoints.
- **S13** Paliers sous le plafond global, drapeau `OTP_CHALLENGE_REQUIRED` désactivé, `503` au plafond dur seulement, SMS sans donnée utilisateur → OTP.
- **S14** Recherche Ops en POST, aucune donnée personnelle dans les URL, filtre de logs étendu, Sentry, motifs Ops énumérés → Endpoints, Données personnelles, Normalisation.
- **S15** Schéma de `metadata` par action, `mask_phone` + `phone_hmac`, nouveaux événements, audit hors transaction → `AuditEvent`, Données personnelles.
- **S16** `purpose` strict, `register_anonymizer()` obligatoire, effacements complets, rotation des sauvegardes → Endpoints, Données personnelles.
- **S17** Compte de revue encadré (SIM Jeflink, marqueur, borne dans le temps, alertes) → OTP.
- **S18** Délai de recyclage non publié au Sénégal, donc règle « compte dormant » (60 j) livrée en V1, `auth_time` + `RequiresRecentAuth`, alerte « nouvelle connexion », script support → Sessions (compte dormant, V1), Rôles, Parcours, Q17 et Q18.
- **S19** Invitation en attente plutôt que compte créé, réponse identique, 20 par jour et par pro → Parcours Pro, `RoleInvitation`, OTP (limites).
- **S20** Stockage sécurisé `WHEN_UNLOCKED_THIS_DEVICE_ONLY`, `allowBackup = false`, `next` validé → Sessions, BFF.
- **S21** gitleaks, check des clés au démarrage, rotation (MultiFernet, `kid`, 2 secrets BFF) → Réglages, Tâches (infra).
- **S22** Déclaration CDP, formalité de transfert, critères DPA dans Q7, registre des traitements → Données personnelles, OTP (fournisseur), Q7.
- **S23** `fake` conditionné à `DJANGO_ENV`, pas à `DEBUG` → OTP (SmsGateway).
- **S24** `/api/schema/` en local, test ou hôte interne seulement → Réglages.
- **S25** Session Ops de 30 min d'inactivité et 12 h au maximum, TOTP de moins de 5 min pour `manage` → Sessions, Rôles.
- **S26** Validation de `display_name` → `User`.
- **S27** E-mail non vérifié jamais utilisé pour la récupération → `User`.
- **S28** Test d'interception de `send_otp` → Tâches Celery.
- **S29** Limite déclarée et testée sur chaque vue `AllowAny` → OTP (limites), Critères.
- **S30** Réactivation après `fraud` par un Ops différent → `User`, Endpoints.
- **S31** Trace IP optionnelle (HMAC du /24 ou du /48 + ASN, 90 j) → Q16.

## Hors périmètre

- **Connexion Google** (Q2). Règle posée dès maintenant : **pas de compte sans téléphone vérifié**. Une première connexion Google inconnue impose un OTP téléphone, puis lie l'identité (modèle futur `accounts.ExternalIdentity`). Aucune fusion de comptes.
- OTP par WhatsApp (V2, canal réservé) et par appel vocal (Q6).
- Changement de numéro en libre-service.
- Écrans console Ops de gestion des comptes : la spec console Ops consommera `ops-accounts`.
- **Push « nouvelle connexion »** pour `owner` et `technician` : au plus tard avec la spec `wallet`.
- Accusés de réception SMS (DLR) : avec l'adaptateur réel.
- Authentification WebSocket (spec temps réel) : jamais de jeton en query string.
- Adaptateurs Play Integrity, App Attest et Turnstile au-delà du drapeau et du point d'extension (activés si la fraude apparaît).
- Passkeys ; codes de secours TOTP (**à livrer avant d'avoir 3 Ops**, Q3) ; second facteur pour les pros (Q14).
- `purpose = sensitive_action` : réservé ici, endpoints fournis par `wallet`.
- Consentement marketing (préférences `notifications`) ; parrainage (`promotions`).
- Contenu `wo` des écrans, du SMS et de l'audio d'aide (clés prévues, Q12).

## Critères d'acceptation

- [ ] Les formes `77 123 45 67`, `771234567`, `00221771234567` et `+221771234567` donnent le même compte. Un fixe sûr renvoie `phone_not_mobile`. Un type `UNKNOWN` est accepté. Un numéro FR donne `phone_region_not_supported`, qui mène à l'écran dédié, tant que FR n'est pas autorisé.
- [ ] `otp/request` a une réponse identique (statut, forme, pas d'écart de temps mesurable) pour un numéro inconnu, un compte actif, un compte désactivé et un numéro qui a déjà des challenges.
- [ ] La même `Idempotency-Key` rejouée avant `resend_available_at` renvoie le même corps sans second SMS.
- [ ] Rouvrir l'app ou l'onglet pendant l'attente du SMS ramène à l'écran code avec le même challenge.
- [ ] `verify` sans `challenge_secret` valide est refusé.
- [ ] `verify` réussi puis rejoué en moins de 2 min (même code, même secret, même `install_id`) rend des jetons pour la même session. Toute autre combinaison renvoie `otp_already_used`.
- [ ] Aucun code en clair en base, dans les logs (Django et BFF) ni dans les arguments de tâche (test d'interception de `apply_async`).
- [ ] Le code du premier SMS reste accepté après deux renvois. Au 5e échec, le challenge passe `locked`. 20 vérifications concurrentes ne produisent au plus qu'un succès et le bon compte d'échecs.
- [ ] Limites : 6e SMS en 1 h pour un numéro, tous motifs confondus, invitations comprises → `429` avec `retry_after`. Blocage progressif après 10 échecs, sans toucher les sessions existantes. Redis coupé → comptage en base ou `503`, jamais d'envoi illimité.
- [ ] Deux IP web derrière le BFF sont comptées séparément. Un `X-Jeflink-Client-Ip` sans secret valide, ou arrivé hors de l'hôte interne, est ignoré.
- [ ] Chaque vue `AllowAny` a une limite déclarée et testée.
- [ ] Gabarits SMS client et Pro en GSM-7, au plus 160 caractères, hachage et ligne WebOTP compris, sans donnée utilisateur (test).
- [ ] Refresh :
  - un refresh interrompu puis rejoué **10 min plus tard** ne déconnecte pas ;
  - un second usage de l'ancien refresh, ou un usage après que le courant a servi, révoque la session et écrit l'audit.
- [ ] Une session révoquée rejette son access en moins de 60 s.
- [ ] Ops :
  - sans jeton d'enrôlement, `setup` renvoie `mfa_enrollment_not_authorized` ;
  - `setup` est refusé si un TOTP est déjà confirmé ;
  - un code TOTP rejoué est refusé ;
  - 10 échecs verrouillent la console ;
  - un compte ops connecté depuis l'app client n'a aucune permission Ops ;
  - une action `manage` avec un TOTP de plus de 5 min renvoie `ops_step_up_required` ;
  - un Ops ne peut pas agir sur lui-même ni sur un autre ops.
- [ ] Changement de numéro : sans l'approbation d'un second Ops sur un compte pro, rien ne se passe. Le code n'apparaît jamais côté Ops. Après confirmation, toutes les sessions sont révoquées et l'ancien numéro reçoit le SMS d'information.
- [ ] Invitation : aucun `User` n'existe avant la connexion et l'acceptation. La réponse côté pro est identique, que le numéro ait un compte ou non.
- [ ] Un invité reçoit `403 profile_incomplete`, puis l'action passe après `PATCH /api/me/`, et ses demandes sont intactes.
- [ ] Session d'un autre utilisateur → 404. Recherche Ops par POST, sans numéro dans aucune URL.
- [ ] La suppression anonymise, efface le libellé d'appareil, `install_id`, OTP et invitations, puis libère le numéro. `purpose ≠ delete_account` est refusé.
- [ ] `otp/verify` pour un compte `is_staff` renvoie `account_not_allowed`.
- [ ] `AuditEvent.metadata` hors schéma de l'action → refus (test). Un audit sur chemin d'erreur survit au rollback.
- [ ] Au démarrage, une clé manquante, trop courte ou dupliquée empêche le lancement. Le build Next ne contient aucun secret dans `.next/static`.
- [ ] Web et console :
  - aucun jeton lisible en JavaScript ;
  - un POST sans `Origin` exact, y compris sur `/api/auth/*`, est refusé ;
  - le proxy refuse `..`, `%2f`, `/api/internal/` et `/api/schema/` ;
  - deux requêtes concurrentes de comptes différents ne se mélangent pas ;
  - `next` externe refusé.
- [ ] Apps :
  - remplissage automatique du code sur Android (hachage de la clé release) et iOS ;
  - « Pas de connexion » distinct de « Code incorrect », saisie conservée ;
  - déconnexion et `session_revoked` purgent caches, brouillons et jeton push ;
  - une action hors ligne n'est jamais rejouée sous un autre `sub`.
- [ ] Chaque erreur d'auth propose le lien support WhatsApp, pré-rempli sans code.
- [ ] Toutes les chaînes et tous les codes d'erreur ont une clé i18n `fr` ; les clés `wo` sont créées.
- [ ] Revues `security-reviewer` (tâches [sécu]) et `design-guardian` (écrans) faites. `make openapi` passe.

## Tâches par couche

Chaque tâche est livrable et testable seule, dans l'ordre indiqué. Une tâche [sécu] exige la revue `security-reviewer` avant fusion.

- infra :
  1. [sécu] gitleaks en pre-commit et en CI.
  2. [sécu] Redis dédié à l'auth : authentification, TLS hors réseau privé, `noeviction`.
  3. Service Celery `beat` dans `infra/docker-compose.yml`.
  4. Reverse proxy : pose `REMOTE_ADDR` (PROXY protocol ou `--proxy-headers` avec liste stricte), rejette `Host: api` et les hôtes inconnus, retire tout en-tête `X-Jeflink-*` venu de l'extérieur, n'expose pas `/api/schema/` ni l'admin en production (accès par réseau, pas par `Host`). `BFF_TRUSTED_NETWORKS` = CIDR du réseau interne du BFF.
- api :
  1. [sécu] **`trust` minimal** : `AuditEvent`, `audit()` avec schémas par action, écriture hors transaction sur les chemins d'erreur, admin en lecture seule, tests.
  2. [sécu] **`common`** : `pii.py` (`mask_phone`, `phone_hmac`), filtre de logs (motifs et clés de S14), `gsm7.py`, tests.
  3. [sécu] **Réglages et checks au démarrage** : `DJANGO_ENV`, check des clés (S21), `CACHES` Redis, restriction de `/api/schema/`, tests.
  4. [sécu] **`User` réécrit** : modèle, gestionnaire, contraintes, validation de `display_name`, `normalize_phone`, migration `0001` régénérée (base locale à recréer), admin en lecture seule, fabriques, tests.
  5. [sécu] **Rôles et permissions** : `RoleGrant`, `grant_role`/`revoke_role`, classes de S5, `RequiresRecentAuth`, groupes Ops, commandes `grant_ops_role`/`revoke_ops_role` (`--operator`, `--reason`, `--second-operator`), tests.
  6. [sécu] **`notifications.sms`** : interface, exceptions, `fake` limité par `DJANGO_ENV`, aucun corps journalisé, tests.
  7. [sécu] **Socle de débit** : compteurs Lua, repli en base, `OtpPhoneBlock`, paliers et plafonds, `TrustedClientIpMiddleware`, tests.
  8. [sécu] **Sessions** : simplejwt avec `kid`, `DeviceSession`, grâce une fois par rotation, cache des sessions actives, `SessionJWTAuthentication`, `token/refresh`, `logout`, `me/sessions*`, tests (dont refresh rejoué 10 min plus tard). **Compte dormant** : détection via `DeviceSession.last_seen_at`, claim `restricted`, permission `IsNotRestricted` appliquée par défaut aux vues de données personnelles, `clear_dormant_restriction` (Ops, audité), « Repartir de zéro », tests.
  9. [sécu] **OTP** : `OtpChallenge`, `OtpDelivery`, `challenge_secret`, idempotence, `request`/`resend`/`verify` (ordre des contrôles, rejeu, `other_sessions`), `send_otp`, gabarits client et Pro, `auth/config`, tests (dont 20 vérifications concurrentes).
  10. [sécu] **Défi client** : drapeau `OTP_CHALLENGE_REQUIRED`, désactivé, et point d'extension de vérification, tests.
  11. **Profil** : `GET`/`PATCH /api/me/`, passage d'invité à complet, `RequiresCompleteProfile`, tests.
  12. [sécu] **Invitations** : `RoleInvitation`, `invite_to_role`, `register_invitation_handler`, `me/invitations*`, SMS générique, limites, tests.
  13. [sécu] **TOTP Ops** : `TotpDevice` (MultiFernet), `OpsEnrollmentToken`, `MfaChallenge`, `mfa/totp/*` dont `step-up`, verrou, `reset_ops_mfa`, recalcul de `mfa` au refresh, tests.
  14. [sécu] **Suppression** : `me/deletion*`, anonymisation, `register_anonymizer`, `register_deletion_blocker`, tests.
  15. [sécu] **Endpoints Ops** : `search`, détail, `reveal-phone`, `revoke-sessions`, `unblock-otp`, `deactivate`/`reactivate`, règles de cible, motifs énumérés, tests.
  16. [sécu] **Changement de numéro** : `PhoneChangeRequest`, approbation par un second Ops, challenge `change_phone`, `phone-change/confirm`, SMS à l'ancien numéro, tests.
  17. [sécu] **Compte de revue des stores** : `create_review_account`, bornes, checks au démarrage, alertes, tests.
  18. **Purge** : `purge_auth_data` + `CELERY_BEAT_SCHEDULE` (y compris les `OtpPhoneBlock` expirés depuis plus de 24 h et les `RetiredRefreshToken` des sessions purgées), tests.
  19. **Contrat et documentation** : `make openapi`. Mise à jour de `apps/api/CLAUDE.md` (Bearer seul, classes de permission, `trust.audit`, `notifications.sms.fake`, `register_anonymizer` dans la définition de « done ») et de `ARCHITECTURE.md`. Registre des traitements et note sur la rotation des sauvegardes (S16, S22). Procédure support écrite (S2, S18).
  20. [sécu] **Adaptateur SMS réel**, bloqué par Q7 : adaptateur, DLR si disponible, tests avec réponses enregistrées.
  21. [sécu] **Second facteur de l'admin Django** (`django-otp` ou équivalent, dépendance justifiée dans la PR), en plus de l'hôte interne (infra 4). Relevé par la revue sécurité du 2026-09-30 : aucune tâche ne le couvrait. Y ajouter une limite de débit sur la page de connexion de l'admin (vue non DRF).
- packages/api-client :
  1. `http.ts` : `Authorization` par appel prioritaire, `onUnauthorized` (un seul refresh, un rejeu), `X-Requested-With`. Tests unitaires.
  2. [sécu] `src/bff/` (`server-only`) :
     - route handlers d'auth et proxy durci ;
     - cookies (`jf_at`, `jf_rt`, `jf_mfa`, `jf_dev`), `Origin` exact, `X-Jeflink-Client-Ip` + secret, `app` imposé ;
     - aucun état de module, en-têtes de cache ;
     - redirection de refresh pour les Server Components et le middleware ;
     - tests (concurrence, traversée de chemin, en-têtes).
- web / console :
  1. [sécu] **web — BFF** : montage, variables serveur, test de build sans secret, `Referrer-Policy` sur `/connexion`, verrou de refresh entre onglets.
  2. **web — `/connexion`** :
     - étapes téléphone, code, autres appareils, nom ;
     - challenge reprenable (`sessionStorage`), WebOTP ;
     - écran « région non couverte », erreurs avec support ;
     - `next` validé, i18n, revue design.
  3. [sécu] **console — BFF** : montage, CSP stricte, politique de session ops.
  4. [sécu] **console — `/connexion` + TOTP** : OTP, puis saisie du jeton d'enrôlement et enrôlement, ou vérification ; fenêtre de step-up ; gardes de route (`/ops`, `/pro`, accès refusé) ; i18n, revue design.
- client / pro :
  1. [sécu] **client — session** : `expo-secure-store` (`WHEN_UNLOCKED_THIS_DEVICE_ONLY`), `allowBackup = false`, `onUnauthorized`, purge à la déconnexion et sur `session_revoked`. Test de coupure pendant le refresh.
  2. **client — écrans OTP** :
     - téléphone, avec `Idempotency-Key` ;
     - code : reprenable, champ toujours actif, « Le SMS peut mettre 3 minutes », renvoi après 60 s, distinction réseau / code faux ;
     - aide en pictogrammes et audio ;
     - écrans « région non couverte » et « autres appareils », nom ;
     - i18n, revue design.
  3. **client — Mon compte** : nom, langue, appareils (libellé et dernière activité), déconnexion, suppression avec OTP.
  4. [sécu] **pro — session + OTP** : mêmes briques, gabarit Pro (hachage Android de l'app Pro), boutons d'au moins 48 px, routage selon `roles`, écran « Devenir pro ».
  5. [sécu] **pro — file hors ligne et changement d'utilisateur** : actions marquées du `sub`, jamais rejouées sous un autre compte, choix « Envoyer d'abord / Supprimer », avertissement à la déconnexion.
  6. **pro — Mon compte + invitations** : appareils, déconnexion, suppression, acceptation ou refus d’invitation, verrou local optionnel (Q19, `expo-local-authentication`, dépendance justifiée dans la PR).

## Questions à trancher (Zay)

Chaque question porte la proposition de l’architecte et, quand il existe, l’avis sécurité ou terrain. Les questions marquées ✅ sont tranchées ; les autres attendent une réponse avant que la spec passe en « validée ».

1. **Q1 — Régions OTP en V1.** ✅ _Tranché par Zay le 2026-09-30._ Sénégal seul (`OTP_ALLOWED_REGIONS = ["SN"]`). Pour la diaspora, l'écran dédié (T3) oriente vers un proche à Dakar ; l'ouverture plus tard ne sera qu'une question de configuration.
2. **Q2 — Google.** ✅ _Proposition acceptée par Zay le 2026-09-30._ Retenu : Google après la V1. Question d'origine : Après la V1 (proposé), ou en fin de V1 pour le web seulement ?
3. **Q3 — Second facteur Ops.** ✅ _Proposition acceptée par Zay le 2026-09-30._ Retenu : TOTP obligatoire pour les Ops, enrôlement selon S1, codes de secours avant le 3e Ops. Question d'origine : _Sécurité_ : TOTP obligatoire, avec l'enrôlement corrigé selon S1, et codes de secours livrés avant d'avoir 3 Ops. D'accord ?
4. **Q4 — Durées de session.** ✅ _Proposition acceptée par Zay le 2026-09-30._ Retenu : mobile 60 j / 180 j, web 30 j / 90 j, Ops 30 min / 12 h (S25). Question d'origine : Mobile 60 j d'inactivité et 180 j au maximum ; web 30 j et 90 j. _Sécurité_ : d'accord sous réserve de S18 (compte dormant, `RequiresRecentAuth`) ; Ops à 30 min d'inactivité et 12 h au maximum (S25).
5. **Q5 — Porte invité → complet.** ✅ _Proposition acceptée par Zay le 2026-09-30._ Retenu : nom exigé pour accepter un devis. Question d'origine : Nom exigé pour accepter un devis (proposé), ou dès la publication ?
6. **Q6 — Repli si le SMS n'arrive pas.** ✅ _Proposition acceptée par Zay le 2026-09-30._ Retenu : renvoi + support WhatsApp ; pas d'OTP vocal en V1. Question d'origine : Renvoi plus support WhatsApp (proposé), ou OTP par appel vocal dès la V1 ?
7. **Q7 — Fournisseur SMS.** ✅ _Tranché par Zay le 2026-09-30._ La société partenaire de Zay compare les offres, choisit le fournisseur, le budget, le plafond quotidien (`SMS_DAILY_CAP`) et porte l'enregistrement de l'expéditeur « JEFLINK ». Critères à lui transmettre : couverture des 3 opérateurs, lieu de traitement et DPA (S22), DLR, tarif par segment GSM-7. La tâche api n° 20 reste bloquée jusqu'à ce choix.
8. **Q8 — Rétention et suppression.** ✅ _Tranché par Zay le 2026-09-30._ Anonymisation et durées (7 j, 30 j, 90 j, 5 ans) soumises au consultant juridique de Jeflink, en même temps que la déclaration CDP. Les durées restent des réglages : les changer ne touche pas le code.
9. **Q9 — Nom.** ✅ _Proposition acceptée par Zay le 2026-09-30._ Retenu : un seul champ `display_name`. Question d'origine : Un seul champ `display_name` (proposé), ou prénom et nom séparés ?
10. **Q10 — Changement de numéro.** ✅ _Proposition acceptée par Zay le 2026-09-30._ Retenu : changement de numéro par l'Ops seulement, procédure S2. Question d'origine : _Sécurité_ : par l'Ops seulement, avec la procédure S2 (deux temps, second Ops, 72 h de refroidissement). D'accord ?
11. **Q11 — Longueur du code.** ✅ _Proposition acceptée par Zay le 2026-09-30._ Retenu : code à 6 chiffres. Question d'origine : _Sécurité_ : 6 chiffres, 4 chiffres est inacceptable. À confirmer.
12. **Q12 — Wolof.** ✅ _Tranché par Zay le 2026-09-30._ La community manager et le commercial rédigent et valident le SMS `wo`, les textes des écrans de connexion et l'audio d'aide. Ils choisissent la graphie : le SMS doit rester en GSM-7 (pas de « ë », « ñ », « ŋ »), alors que les écrans et l'audio peuvent utiliser la graphie officielle. À produire tôt (terrain).
13. **Q13 — Compte de revue des stores.** ✅ _Proposition acceptée par Zay le 2026-09-30._ Retenu : compte de revue des stores, avec S17 complet. Question d'origine : _Sécurité_ : acceptable seulement avec S17 complet. D'accord ?
14. **Q14 — Pros sur la console web.** ✅ _Proposition acceptée par Zay le 2026-09-30._ Retenu : pros sur la console web : OTP seul tant qu'il n'y a pas d'argent. Question d'origine : _Sécurité_ : OTP seul tant que la console Pro ne touche pas à l'argent. D'accord ?
15. **Q15 — Fenêtre de grâce du refresh : 24 h (retenu) ou 60 s ?** ✅ _Proposition acceptée par Zay le 2026-09-30._ Retenu : grâce du refresh de 24 h, une seule fois par rotation. Question d'origine :
    - Risque à 24 h : un refresh ancien volé peut servir une fois, tant que le vrai client n'a pas encore utilisé le courant. La prise de contrôle est bornée et détectée au refresh suivant du vrai client, mais la fenêtre est longue.
    - Risque à 60 s : un utilisateur sur réseau instable qui perd la réponse et réessaie plus tard est déconnecté (nouvel OTP, coût SMS, abandon).
16. **Q16 — Trace IP optionnelle (S31).** ✅ _Proposition acceptée par Zay le 2026-09-30._ Retenu : aucune trace IP conservée tant qu'aucune fraude n'apparaît. Question d'origine : Conserver un HMAC du /24 (IPv4) ou du /48 (IPv6) plus l'ASN pendant 90 j, pour enquêter sur la fraude ? Ou ne rien conserver (proposé tant qu'il n'y a pas de fraude) ?
17. **Q17 — Compte dormant.** ✅ _Tranché par Zay le 2026-09-30._ **60 jours** d'inactivité. Règle livrée en V1 (voir « Sessions et jetons »).
18. **Q18 — Délai de recyclage des numéros.** ✅ _Recherche faite le 2026-09-30 (sources publiques)._ Aucune règle sénégalaise publique n'a été trouvée (ARTP, Orange, Yas). Référence régionale : ARTP-Togo, 3 mois d'inactivité puis réattribution 3 mois après désactivation. Au Sénégal, plus de 1,5 million de numéros ont été désactivés en 2025. Conséquence : la règle « compte dormant » passe en V1. Reste ouvert, sans bloquer : une confirmation écrite de l'ARTP ou d'un opérateur, que seule l'entreprise peut demander.
19. **Q19 — Verrou local de l'app Pro** ✅ _Proposition acceptée par Zay le 2026-09-30._ Retenu : verrou local de l'app Pro livré en V1, **optionnel** (désactivé par défaut, activable dans « Mon compte »). Question d'origine : (code ou biométrie de l'appareil, `expo-local-authentication`) : oui ou non en V1 ?
20. **Q20 — Pompage de SMS et plafond global** (revue sécurité de la tâche 7). Un attaquant qui vise des numéros au hasard peut épuiser `SMS_DAILY_CAP` en quelques heures : toutes les nouvelles connexions répondent alors 503 pour la journée. Deux parades à arbitrer :
    - (a) réserver une part du plafond global aux numéros qui ont déjà un compte (les campagnes de pompage visent des numéros inconnus) ;
    - (b) inscrire dans la procédure d'alerte : à 50 %/80 % du plafond, activer `OTP_CHALLENGE_REQUIRED` (attestation d'appareil, CAPTCHA web).
