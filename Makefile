API = uv run --directory apps/api

.PHONY: install api web demo demo-reset test admin

# Dépendances Python (uv) et JS (pnpm), base SQLite à jour.
install:
	$(API) python manage.py migrate
	pnpm install

api:        ; $(API) python manage.py runserver 8000
web:        ; pnpm dev
test:       ; $(API) pytest
# Métiers, quartiers, comptes de démo et demandes à chaque étape (mot de passe : voir README).
demo:       ; $(API) python manage.py migrate && $(API) python manage.py seed_demo
demo-reset: ; $(API) python manage.py seed_demo --reset
admin:      ; $(API) python manage.py createsuperuser
