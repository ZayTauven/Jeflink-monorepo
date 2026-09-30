# ADR 0007 — Sessions : JWT court, refresh opaque en base, BFF Next à cookies

Statut : proposé · 2026-09-30 · Spec : `docs/specs/001-accounts.md` · Amende ADR 0006

## Contexte

Quatre fronts consomment la même API : deux apps Expo (client, pro) et deux Next (web, console). L'identifiant est le téléphone vérifié par OTP ; il n'y a pas de mot de passe. Sur le terrain, le réseau coupe en plein échange, un pro reste hors ligne plusieurs jours, un téléphone se perd ou se partage en famille, et chaque connexion coûte un SMS. Les comptes Ops ont des pouvoirs sensibles, et l'échange de SIM est une fraude connue. DRF tourne aujourd'hui en `SessionAuthentication`, et `configureApiClient()` est un singleton de module, donc dangereux côté serveur Next.

## Décision

- **Access** : JWT simplejwt, HS256, clé choisie par `kid` parmi 2 clés en rotation. Durée de 15 min, 10 min pour les Ops. Claims : `sub`, `sid`, `auth_time`, `mfa`, `mfa_at`. Aucun rôle dans le jeton.
- **Refresh** : jeton opaque haché dans `accounts.DeviceSession`, une ligne par appareil, rotation à chaque usage.
  - **Grâce** : l'ancien refresh est accepté une seule fois par rotation (verrou de ligne), seulement si le refresh courant n'a jamais été présenté, et pendant 24 h au plus. La grâce renvoie le refresh courant, sans nouvelle rotation.
  - Toute autre présentation d'un ancien refresh est une réutilisation : la session est révoquée et un `AuditEvent` est écrit.
  - Le compromis 24 h contre 60 s est soumis à Zay.
- **Session active vérifiée à chaque requête** : cache Redis `auth:sid:<sid>` (60 s, écrit en `on_commit`, supprimé à la révocation), repli sur la base. Le Redis d'auth est authentifié et sans éviction.
- **Mobile** : refresh dans `expo-secure-store` (`WHEN_UNLOCKED_THIS_DEVICE_ONLY`), sauvegarde Android désactivée, access en mémoire.
- **Web et console : BFF Next.**
  - Jetons en cookies `__Host-jf_at` et `__Secure-jf_rt` (`Path=/api/auth`, jamais élargi). `mfa_token` en `__Host-jf_mfa`.
  - Le refresh n'a lieu que dans le route handler dédié, avec un verrou entre onglets.
  - Aucun état de module côté serveur, aucune mise en cache des données authentifiées.
  - Proxy durci : chemins, liste fermée d'en-têtes, préfixes interdits.
  - Contrôle `Origin` exact, y compris sur `/api/auth/*`.
  - L'IP cliente passe par `X-Jeflink-Client-Ip`, cru seulement avec un secret partagé (2 valeurs en rotation) **et** une arrivée par l'hôte interne.
  - Django n'accepte que le Bearer : ni session, ni CSRF, ni CORS côté API.
- **Ops** :
  - TOTP obligatoire depuis la console, enrôlé seulement avec un jeton hors bande ;
  - `HasOpsPerm` exige `mfa`, et un `mfa_at` de moins de 5 min pour les actions `manage` ;
  - session de 30 min d'inactivité et 12 h au maximum ;
  - le refresh recalcule `mfa`.
- **Amendement de l'ADR 0006** : `packages/api-client/src/bff/` (`server-only`) devient le seul second `fetch` autorisé. Côté serveur, le jeton passe par appel. `jeflinkFetch` gagne `onUnauthorized` : un seul refresh à la fois, puis un rejeu.

## Conséquences

- Presque aucun SMS de reconnexion. Aucune déconnexion due à une coupure réseau, même longue.
- « Appareils connectés » : révocation effective en moins de 60 s.
- Aucun jeton exposé au JavaScript du navigateur. Web et console ont des sessions séparées.
- Permissions Ops inutilisables sans second facteur récent.
- − Nous maintenons notre propre table de sessions, la rotation et la grâce : du code sensible, avec revue sécurité obligatoire.
- − Une lecture Redis par requête authentifiée, et une base Redis dédiée à configurer en production.
- − Le BFF est une pièce de plus à héberger, avec des règles strictes (cache, en-têtes, proxy) à tester.
- − La vérification multi-clés par `kid` est une surcouche à simplejwt.

## Alternatives écartées

- **Refresh simplejwt + `token_blacklist`** : pas de révocation de famille, pas de grâce contrôlée, pas de liste d'appareils.
- **Sessions Django partout** : mal adaptées au mobile, et deux systèmes à maintenir.
- **Jetons en `localStorage` côté web** : exposés à la moindre faille XSS.
- **Fournisseur d'identité tiers** (Firebase Auth, Auth0, Supabase) : pas de maîtrise du coût ni de la délivrabilité des SMS au Sénégal, données hors de notre contrôle (CDP), dépendance forte.
