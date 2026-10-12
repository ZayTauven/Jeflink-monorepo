# apps/api — API Django de la démo

Django 5.2 + DRF + drf-spectacular, base SQLite (`db.sqlite3`, ignorée par git). Un seul fichier de réglages : `jeflink/settings.py`.

| App        | Contenu                                                                 |
| ---------- | ----------------------------------------------------------------------- |
| `accounts` | `User` (connexion par email, rôle client/pro, téléphone E.164), `ProProfile`, `ContactMessage` ; `/api/auth/…` |
| `catalog`  | `Trade` (métier), `Zone` (quartier) ; lecture publique : métiers, quartiers, pros vérifiés, avis, chiffres |
| `jobs`     | `ServiceRequest`, `Quote`, `Review`, `RequestEvent` ; `/api/requests/…` ; commande `seed_demo` |
| `console`  | API de la console d'administration, réservée à l'équipe (`IsAdminUser`) : `/api/console/…` ; chiffres dans `stats.py`, actions dans `services.py`, `AuditLog` (journal) |

- Règles métier dans `jobs/services.py` uniquement (qui voit quoi, devis, choix, fin, annulation, avis). Les vues valident l'entrée et appellent le service.
- Cycle d'une demande : `open → booked → done`, annulation possible avant la fin (client, ou équipe avec motif). 3 devis au plus. Seul un pro **vérifié** (console → Pros) peut chiffrer.
- Argent : `accept_quote` fige prix, remise (`Coupon`, financée par Jeflink), taux et montant de commission sur la demande ; `console/finance.py` calcule transactions, soldes des pros (`ProSettlement`) et rapports. Jamais de float.
- Litiges (`Dispute`) : ouverts par le client, le pro de la mission ou l'équipe sur une mission réservée ou terminée, un seul actif à la fois ; clore exige une décision écrite. Règles dans `jobs/services.py`.
- Console : chaque vue déclare sa rubrique (`console_section`) ; `console/permissions.py` dit quels rôles (`User.staff_role`, super admin pour un superuser) y ont accès. Réglages de la plateforme : `PlatformSettings.load()` (devis maximum, pause des demandes, support), lus par `jobs.services`.
- Console : toute action de l'équipe passe par `console/services.py` et écrit une ligne `AuditLog` (lecture seule dans l'admin Django). Avis masqué = hors du site, de la note du pro et des chiffres publics.
- Argent : `PositiveIntegerField` en F CFA.
- Documentation interactive : http://localhost:8000/api/docs/ · back-office : http://localhost:8000/admin/
- Tests : `tests/test_flow.py` (parcours complet + règles de confiance), `tests/test_console.py` (accès équipe, chiffres). Chaque nouvelle règle a son test.
- `seed_demo` ajoute 90 jours d'historique (graine fixe, dates antidatées après passage par `services`) pour les graphiques de la console.
- Lint : `uv run ruff check .` et `uv run ruff format .` (le hook de Claude formate déjà).
