# ADR 0008 — SMS derrière une interface `SmsGateway`

Statut : accepté · 2026-09-30 · Spec : `docs/specs/001-accounts.md`

## Contexte

L'OTP par SMS est la porte d'entrée de Jeflink, et le SMS sert aussi de repli aux notifications critiques et aux messages de service (invitation d'un technicien, information après un changement de numéro). Le fournisseur n'est pas choisi. Parmi les candidats : Orange (API SMS), Infobip, Twilio, Vonage, Africa's Talking, agrégateurs locaux. Prix, délivrabilité par opérateur (Orange, Free/Yas, Expresso), enregistrement de l'expéditeur « JEFLINK », lieu de traitement et contrat de sous-traitance (CDP) restent à comparer. Les endpoints d'OTP sont une cible de fraude par pompage de SMS. WhatsApp (V2) et peut-être l'appel vocal viendront s'ajouter comme canaux. Les tests ne doivent jamais toucher le réseau.

## Décision

- Interface `SmsGateway` dans `jeflink/notifications/sms/`, sur le modèle de `PaymentGateway` (ADR 0002) :
  - méthode `send(*, to, body, idempotency_key, sender_id) -> SmsResult` ;
  - trois exceptions : `SmsTransientError` (nouvel essai possible), `SmsAmbiguousError` (pas de nouvel essai) et `SmsPermanentError`.
- Adaptateurs : `fake`, puis un adaptateur par fournisseur choisi.
  - `fake` est autorisé seulement si `DJANGO_ENV ∈ {local, test}`, et non selon `DEBUG`.
  - Aucun adaptateur ne journalise les corps HTTP.
- **Jeflink génère et hache lui-même les codes OTP**, dans le worker. Le fournisseur ne fait que transporter un texte.
- **Gabarits** :
  - chaînes traduites, en GSM-7, au plus 160 caractères, **sans aucune donnée utilisateur** ;
  - gabarits distincts pour l'app client et l'app Pro ;
  - hachage Android (SMS Retriever) obligatoire par app et par clé de signature, et ligne WebOTP.
- **Plafonds** :
  - par numéro, tous motifs confondus ;
  - par préfixe opérateur et par bloc de numéros ;
  - global quotidien, avec alertes à 50 % et 80 % et `503` au plafond dur ;
  - ralentissement si le taux de conversion s'effondre.
  - Les compteurs sont atomiques et ne tombent jamais en mode ouvert.
  - Le drapeau `OTP_CHALLENGE_REQUIRED` (attestation d'appareil, CAPTCHA web) est livré désactivé.
- Aucun domaine n'appelle un fournisseur SMS directement.

## Conséquences

- Changer de fournisseur, ou en utiliser deux (par opérateur, ou en secours), revient à écrire un adaptateur.
- La logique OTP est testable sans réseau et ne dépend d'aucun fournisseur.
- Le coût et la délivrabilité sont mesurables par envoi et par préfixe opérateur.
- − Nous portons nous-mêmes la sécurité de l'OTP (génération, hachage, limites, anti-fraude), que Verify aurait fournie.
- − Chaque adaptateur doit classer correctement ses erreurs. Une erreur mal classée peut provoquer un double envoi ou un code perdu.
- − Un fournisseur étranger impose une formalité de transfert de données auprès de la CDP.

## Alternatives écartées

- **Service d'OTP géré (Twilio Verify, Firebase Phone Auth)** : coût par vérification élevé, peu de maîtrise sur la délivrabilité locale, code et données chez un tiers, dépendance forte.
- **Appels directs au fournisseur depuis `accounts`** : impossible à tester sans réseau et à remplacer, et à dupliquer pour les notifications.
