COMPOSE = docker compose -f infra/docker-compose.yml
API     = $(COMPOSE) exec api uv run

.PHONY: up down logs migrate makemigrations api-test openapi shell

up:            ; $(COMPOSE) up -d --build
down:          ; $(COMPOSE) down
logs:          ; $(COMPOSE) logs -f api worker
migrate:       ; $(API) python manage.py migrate
makemigrations:; $(API) python manage.py makemigrations
api-test:      ; $(API) pytest -q
shell:         ; $(API) python manage.py shell
openapi:
	$(API) python manage.py spectacular --file schema.yaml
	pnpm --filter @jeflink/api-client generate
