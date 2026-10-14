# apps/api — API Django de la démo

Django 5.2 + DRF + drf-spectacular, base SQLite (`db.sqlite3`, ignorée par git). Un seul fichier de réglages : `jeflink/settings.py`.

| App        | Contenu                                                                 |
| ---------- | ----------------------------------------------------------------------- |
| `accounts` | `User` (connexion par email, rôle client/pro, téléphone E.164), `ProProfile`, `ContactMessage` ; `/api/auth/…` |
| `catalog`  | `Trade` (métier), `City` (ville, dans une des 14 régions ; fermée = ses quartiers sortent du site), `Zone` (quartier d'une ville, `served_zones()`) ; lecture publique : métiers, quartiers, pros vérifiés, avis, chiffres |
| `jobs`     | `ServiceRequest`, `Quote`, `Review`, `RequestEvent` ; `/api/requests/…` ; commande `seed_demo` |
| `jef`      | Jef, l'assistant de réservation : `JefSession`, `ai.py` (Claude, SDK `anthropic`), `guide.py` (mode sans clé), `services.py` ; `/api/jef/…` |
| `console`  | API de la console d'administration, réservée à l'équipe (`IsAdminUser`) : `/api/console/…` ; chiffres dans `stats.py`, actions dans `services.py`, `AuditLog` (journal) |

- Règles métier dans `jobs/services.py` uniquement (qui voit quoi, devis, choix, fin, annulation, avis). Les vues valident l'entrée et appellent le service.
- Cycle d'une demande : `open → booked → done`. Annulation avant la fin : par l'équipe (motif), ou par le client avec un motif (`CancelReason`, « Autre » = précision obligatoire). Demande ouverte : annulée tout de suite. Mission réservée : `booked → cancelling` (« Annulation demandée ») ; le support rappelle le client puis confirme (`cancelled`, code promo rendu) ou maintient (`booked`) depuis la console, note de l'appel au journal. D'ici là, la mission reste dans les comptes ; les chiffres ne comptent que la première réservation (`finance.first_bookings`). Le motif n'est visible que du client et de l'équipe ; l'historique, que voit aussi le pro, reste neutre. 3 devis au plus. Seul un pro **vérifié** (console → Pros) peut chiffrer.
- Code promo : le client l'ajoute à sa demande (`promo_code`, à la publication ou via `/code/`), vérifié tout de suite (`coupon_problem`) ; chaque devis porte `with_code` (prix après remise pour le client) ; le code s'applique au devis choisi.
- Argent : `accept_quote` fige prix, remise (`Coupon`, financée par Jeflink), taux et montant de commission sur la demande ; `console/finance.py` calcule transactions, soldes des pros (`ProSettlement`) et rapports. Jamais de float.
- Litiges (`Dispute`) : ouverts par le client, le pro de la mission ou l'équipe sur une mission réservée ou terminée, un seul actif à la fois ; clore exige une décision écrite. Règles dans `jobs/services.py`.
- Console : chaque vue déclare sa rubrique (`console_section`) ; `console/permissions.py` dit quels rôles (`User.staff_role`, super admin pour un superuser) y ont accès. Réglages de la plateforme : `PlatformSettings.load()` (devis maximum, pause des demandes, support), lus par `jobs.services`.
- Console : toute action de l'équipe passe par `console/services.py` et écrit une ligne `AuditLog` (lecture seule dans l'admin Django). Avis masqué = hors du site, de la note du pro et des chiffres publics.
- Argent : `PositiveIntegerField` en F CFA.
- Jef : la clé `ANTHROPIC_API_KEY` est lue dans `apps/api/.env` (chargé par `settings.py`, jamais versionné). Les tests n'appellent jamais Claude (`tests/conftest.py` vide la clé ; `test_jef.py` simule les réponses).
- Documentation interactive : http://localhost:8000/api/docs/ · back-office : http://localhost:8000/admin/
- Tests : `tests/test_flow.py` (parcours complet + règles de confiance), `tests/test_console.py` (accès équipe, chiffres). Chaque nouvelle règle a son test.
- `seed_demo` ajoute 90 jours d'historique (graine fixe, dates antidatées après passage par `services`) pour les graphiques de la console.
- Lint : `uv run ruff check .` et `uv run ruff format .` (le hook de Claude formate déjà).
