# apps/api — Django

Stack : Django 5.2 LTS, DRF, drf-spectacular, PostGIS (GeoDjango), Celery + Redis, Channels, PyJWT (sessions maison, ADR 0007), pyotp, uv, ruff, pytest-django, factory_boy.

## Domaines (une app Django par domaine, dans `apps/api/jeflink/`)

`accounts` · `zones` · `catalog` · `providers` · `requests` (demandes + devis) · `bookings` · `payments` · `wallet` · `reviews` · `messaging` · `notifications` · `trust` (KYC, litiges, garantie) · `promotions` · `analytics` · `ai`

Un domaine n'importe jamais les `models` d'un autre pour écrire : il appelle ses `services`.

## Structure d'un domaine

```
<domaine>/
  models.py      # modèles minces, contraintes en base (CheckConstraint, UniqueConstraint)
  services.py    # TOUTE écriture métier ; fonctions typées, transaction.atomic
  selectors.py   # lectures optimisées (select_related / prefetch)
  api/           # serializers + views DRF ; aucune logique métier ici
  tasks.py       # Celery, idempotent (clé d'idempotence), retry borné
  admin.py
  tests/         # test_services.py, test_api.py, factories.py
```
Le skill `jeflink-django-domain` contient les gabarits. `/domain <nom>` génère le squelette.

## Conventions

- Identifiants publics : UUID (`public_id`). L'`id` entier ne sort jamais de l'API. Exception : les données de référence (métiers, services, zones) sont identifiées par leur **slug**, figé après création (URL SEO, IA ; spec 002).
- Argent : `PositiveBigIntegerField` en XOF. Helper `money.format_xof()` pour l'affichage.
- Géo : `PointField(srid=4326)`. Une zone est un centre et un rayon ; son contour (`MultiPolygonField`) est optionnel et prime sur le cercle. Plusieurs zones possibles pour un point : le client choisit (`zones.selectors.zones_for_point`).
- Recherche par les mots des clients : `jeflink.common.search` (`normalize`, `match`), miroir TS dans `@jeflink/api-client/search`, mêmes vecteurs de test.
- Réservations : transitions uniquement via `bookings.services.transition(booking, to=, actor=, actor_kind=, reason=)` ; elle naît à `accepted` par `create_from_quote` (ADR 0010). Un test d'architecture interdit d'écrire `Booking.status` ailleurs que dans `bookings/services.py` (idem pour `ServiceRequest.status` hors `requests/services.py`).
- Demande, devis, réservation (spec 003) : durées et limites en réglages (`REQUEST_*`, `QUOTE_*`, `BOOKING_*`), jamais en dur. Les créations (demande, devis) exigent `Idempotency-Key` (`common.api.idempotency`) ; un rejeu rend la même ressource en `200`. Ordre des verrous : comptes (par id), fiche pro, demande, réservation. Le contact (numéros, repère, position) n'est divulgué qu'aux statuts de `bookings.machine.DISCLOSED_STATUSES` ; avant, les numéros d'un texte libre sont masqués (`common.pii.mask_numbers`). Un domaine qui réagit à la suspension d'un pro s'inscrit par `providers.services.register_suspension_handler`.
- Fin de mission (spec 004) : `transition()` accepte `metadata` (schéma fermé de `BookingEvent`) et `fields` (colonnes de `TRANSITION_FIELDS`, dont `amount_xof`) ; un test d'architecture interdit d'écrire `Booking.amount_xof` ailleurs que dans `bookings/services.py` (création et `accept_amendment`). Une action du pro rejouée rend l'état courant en `200`, sans événement. Un domaine qui réagit à la clôture s'inscrit par `bookings.services.register_close_handler(fn)` (appelé dans la transaction, idempotent par réservation). Le code de fin (`common.crypto`, `DATA_ENCRYPTION_KEYS`) ne sort que par `visible_completion_code` côté client. `trust` n'importe jamais `bookings.services` : le litige est enregistré dans l'admin depuis `bookings`.
- Notifications métier : `notifications.events.notify(kind, recipients, ref)`, après commit, `public_id` seulement (jamais nom, numéro, repère, texte libre).
- Commandes de démonstration (`seed_demo_pros`, `demo_pro`, `make demo`) : `DJANGO_ENV=local` seulement ; les pros `is_demo` sont refusés hors local/test (contrôle `providers.E001`).
- Authentification : Bearer JWT seulement (`SessionJWTAuthentication`), ni session Django, ni CSRF, ni CORS côté API. Le web et la console passent par le BFF Next.
- Permissions (`jeflink/accounts/permissions.py`) : `IsClient` (par défaut ; refuse les sessions restreintes, les comptes inactifs, supprimés ou techniques), `AllowRestrictedSession` (liste blanche testée), `RequiresCompleteProfile`, `RequiresRecentAuth(max_age)`, `HasOwnerRole`, `HasTechnicianRole`, `HasOpsPerm("ops.<domaine>.<action>", step_up=…)` (paramètre explicite, jamais `is_superuser`). `IsVerifiedPro` : rôle `owner` et fiche `verified` (`403 provider_not_verified` sinon), et pose `request.provider`. `IsProOwner` : classe objet (`obj.provider.owner_id == user.id`), à combiner avec `HasOwnerRole` (lecture : une fiche suspendue lit encore) ou `IsVerifiedPro` (écriture) ; les sélecteurs doublent le contrôle et un objet d'un autre répond `404`. `IsTechnicianAssigned` refuse par défaut jusqu'à l'étape 4 (affectation des techniciens).
- Vues publiques : toute vue `AllowAny` déclare `rate_limit_scope` (portée dans `IP_RATE_LIMITS`) et garde `IpRateThrottle` (test S29). Une limite ne s'ouvre jamais quand Redis tombe.
- SMS : uniquement via `jeflink.notifications.sms` (`SmsGateway`) ; l'adaptateur `fake` n'est permis qu'en `local`/`test`. Gabarits GSM-7 testés, sans donnée d'un utilisateur.
- Toute action sensible (argent, statut, KYC, auth) écrit un `AuditEvent` via `jeflink.trust.services.audit()`. Chaque action déclare d'abord le schéma fermé de ses métadonnées (`register_audit_schema`, dans le `ready()` du domaine). Sur un chemin d'erreur qui sera annulé (rollback), on passe `durable=True`.
- Données personnelles : `jeflink.common.pii` (`mask_phone`, `phone_hmac`, `redact`). Jamais de numéro en clair dans un log, une métadonnée d'audit, une URL ou un message d'erreur. Les logs passent par `PiiRedactingFilter`.
- Suppression du compte : un domaine qui stocke des données personnelles enregistre un anonymiseur (`accounts.deletion.register_anonymizer`, écritures en base seulement, effets externes après commit). Un domaine qui peut refuser la suppression (`register_deletion_blocker`) crée ses objets bloquants **sous le verrou du compte** (`User.objects.select_for_update(no_key=True)`) et vérifie `is_active`/`deleted_at` sur la ligne verrouillée.
- Compte de revue des stores (`User.is_review_account`) : ses données ne sont jamais diffusées aux vrais pros.
- Environnement : `DJANGO_ENV` (`local`, `test`, `staging`, `production`) décide de ce qui est permis (adaptateurs `fake`, schéma OpenAPI) ; `DEBUG` n'en décide jamais. Les secrets sont vérifiés au démarrage (`jeflink.common.secrets`).
- Pagination par curseur sur les listes consommées par le mobile.
- Fichiers : stockage S3-compatible (SeaweedFS en dev, `make bucket`) par `common.storage` (`put`, `signed_url`, URL de 10 min signées pour `S3_PUBLIC_ENDPOINT`) ; toute image passe par `common.images.reencode` (WebP sans métadonnée) avant d'être écrite ; clés d'objet faites de `public_id` seulement ; miniatures générées en tâche Celery. En test, `InMemoryStorage` (vidé à chaque test).

## Définition de « fini » pour un domaine

Tests + migrations + `make openapi` + clés i18n des codes d'erreur + schémas d'audit déclarés + anonymiseur enregistré (et testé) si le domaine stocke des données personnelles + revue `security-reviewer` pour toute tâche [sécu].

## Tests

- Chaque service a ses tests. Chaque endpoint : cas autorisé, cas refusé, cas invalide.
- Un chemin qui écrit un audit `durable=True` (connexion `audit`) se teste en mode transactionnel : `pytest.mark.django_db(transaction=True, databases="__all__", serialized_rollback=True)`.
- Pas de réseau en test : gateways de paiement et IA remplacés par leurs fakes (`payments.gateways.fake`, `ai.providers.fake`).
