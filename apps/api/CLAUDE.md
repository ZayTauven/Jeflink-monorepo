# apps/api — Django

Stack : Django 5.2 LTS, DRF, drf-spectacular, PostGIS (GeoDjango), Celery + Redis, Channels, simplejwt, uv, ruff, pytest-django, factory_boy.

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

- Identifiants publics : UUID (`public_id`). L'`id` entier ne sort jamais de l'API.
- Argent : `PositiveBigIntegerField` en XOF. Helper `money.format_xof()` pour l'affichage.
- Géo : `PointField(srid=4326)` ; zones en `MultiPolygonField`. Distances en `geography=True`.
- Réservations : transitions uniquement via `bookings.services.transition(booking, to, actor, reason)`.
- Permissions : classes DRF par rôle (`IsClient`, `IsProOwner`, `IsTechnicianAssigned`, `HasOpsPerm("…")`).
- Toute action sensible (argent, statut, KYC) écrit un `AuditEvent`.
- Pagination par curseur sur les listes consommées par le mobile.
- Fichiers : stockage S3-compatible (SeaweedFS en dev) ; miniatures générées en tâche Celery.

## Tests

- Chaque service a ses tests. Chaque endpoint : cas autorisé, cas refusé, cas invalide.
- Pas de réseau en test : gateways de paiement et IA remplacés par leurs fakes (`payments.gateways.fake`, `ai.providers.fake`).
