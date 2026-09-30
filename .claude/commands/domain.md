---
description: Générer le squelette d'un domaine Django Jeflink
argument-hint: <nom_du_domaine>
---

Crée le domaine `$ARGUMENTS` dans `apps/api/jeflink/` en suivant exactement le skill `jeflink-django-domain` :
models.py, services.py, selectors.py, api/ (serializers, views, urls), tasks.py, admin.py, apps.py, tests/ (factories.py, test_services.py, test_api.py).

Enregistre l'app dans les settings et les URLs. Crée un modèle minimal seulement si je l'ai décrit ; sinon laisse des fichiers vides documentés.
Termine par `make api-test`.
