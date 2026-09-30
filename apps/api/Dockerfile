FROM python:3.13-slim

# GeoDjango : GDAL, GEOS et PROJ sont requis par django.contrib.gis.
RUN apt-get update \
 && apt-get install -y --no-install-recommends binutils gdal-bin libproj-dev \
 && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.12 /uv /uvx /usr/local/bin/

# Le venv vit hors de /app : le montage du code en dev (docker-compose) ne l'écrase pas.
ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_LINK_MODE=copy \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project
COPY . .

EXPOSE 8000
CMD ["uv", "run", "--frozen", "python", "manage.py", "runserver", "0.0.0.0:8000"]
