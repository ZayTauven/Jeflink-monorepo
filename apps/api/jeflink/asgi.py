import os

from django.core.asgi import get_asgi_application

# Channels (chat, statut de réservation, position « en route ») viendra se brancher ici.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "jeflink.settings.local")
application = get_asgi_application()
