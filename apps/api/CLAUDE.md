# apps/api — API Django de la démo

Django 5.2 + DRF + drf-spectacular, base SQLite (`db.sqlite3`, ignorée par git). Un seul fichier de réglages : `jeflink/settings.py`.

| App        | Contenu                                                                 |
| ---------- | ----------------------------------------------------------------------- |
| `accounts` | `User` (connexion par email, rôle client/pro, téléphone E.164), `ProProfile`, `ContactMessage` ; `/api/auth/…` |
| `catalog`  | `Trade` (métier), `Zone` (quartier) ; lecture publique : métiers, quartiers, pros vérifiés, avis, chiffres |
| `jobs`     | `ServiceRequest`, `Quote`, `Review`, `RequestEvent` ; `/api/requests/…` ; commande `seed_demo` |

- Règles métier dans `jobs/services.py` uniquement (qui voit quoi, devis, choix, fin, annulation, avis). Les vues valident l'entrée et appellent le service.
- Cycle d'une demande : `open → booked → done`, annulation possible avant la fin. 3 devis au plus. Seul un pro **vérifié** (case cochée dans l'admin) peut chiffrer.
- Argent : `PositiveIntegerField` en F CFA.
- Documentation interactive : http://localhost:8000/api/docs/ · back-office : http://localhost:8000/admin/
- Tests : `tests/test_flow.py` (parcours complet + règles de confiance). Chaque nouvelle règle a son test.
- Lint : `uv run ruff check .` et `uv run ruff format .` (le hook de Claude formate déjà).
