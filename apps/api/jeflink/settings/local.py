from .base import *  # noqa: F403
from .base import env

DJANGO_ENV = env("DJANGO_ENV", default="local")
SERVE_API_SCHEMA = True
DEBUG = env.bool("DEBUG", default=True)
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["localhost", "127.0.0.1", "api"])
