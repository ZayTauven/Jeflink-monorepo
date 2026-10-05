COMPOSE = docker compose -f infra/docker-compose.yml
API     = $(COMPOSE) exec api uv run

.PHONY: up down logs migrate makemigrations api-test openapi shell seed demo bucket

up:
	$(COMPOSE) up -d --build
	-@sleep 5; $(MAKE) --no-print-directory bucket
down:          ; $(COMPOSE) down
logs:          ; $(COMPOSE) logs -f api worker
migrate:       ; $(API) python manage.py migrate
makemigrations:; $(API) python manage.py makemigrations
api-test:      ; $(API) pytest -q
shell:         ; $(API) python manage.py shell
seed:          ; $(API) python manage.py seed_reference_data
# Local seulement : crée le bucket de photos (SeaweedFS), sans effet s'il existe déjà (ADR 0011).
bucket:        ; $(API) python manage.py ensure_bucket
# Local seulement : catalogue, zones et taux, 3 pros de démonstration vérifiés (spec 003),
# canaux de règlement factices (spec 005).
demo:          ; $(API) python manage.py seed_reference_data && $(API) python manage.py seed_demo_pros && $(API) python manage.py seed_settlement_channels
openapi:
	$(API) python manage.py spectacular --file schema.yaml
	pnpm --filter @jeflink/api-client generate
