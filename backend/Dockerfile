# syntax=docker/dockerfile:1
FROM python:3.12.14-slim-bookworm AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app

# Debian Bookworm main, paquet signé, version observée/pinnée. Licence et notices
# conservées sous /usr/share/doc/stockfish ; aucun téléchargement au runtime.
RUN apt-get update \
    && apt-get install -y --no-install-recommends stockfish=15.1-4 \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt ./
# Facultatif : certificat du proxy de build, jamais copié dans l'image.
# Sans proxy spécifique, pip conserve sa vérification TLS standard.
RUN --mount=type=secret,id=pip_ca \
    if [ -f /run/secrets/pip_ca ]; then export PIP_CERT=/run/secrets/pip_ca; fi; \
    pip install --no-cache-dir -r requirements.txt

COPY --chown=10001:10001 backend/app ./app
RUN useradd --uid 10001 --create-home appuser
USER appuser

FROM base AS test
COPY --chown=10001:10001 backend/requirements-dev.txt backend/pytest.ini ./backend/
COPY --chown=10001:10001 backend/tests ./backend/tests
COPY --chown=10001:10001 retrieval ./retrieval
COPY --chown=10001:10001 tools/openings ./tools/openings
COPY --chown=10001:10001 scripts ./scripts
COPY --chown=10001:10001 .env.example ./.env.example
COPY --chown=10001:10001 backend/app ./backend/app
ENV PYTHONPATH=/app/backend:/app
USER root
RUN --mount=type=secret,id=pip_ca \
    if [ -f /run/secrets/pip_ca ]; then export PIP_CERT=/run/secrets/pip_ca; fi; \
    pip install --no-cache-dir -r backend/requirements-dev.txt \
    && mkdir -p /app/work && chown 10001:10001 /app/work
USER appuser
WORKDIR /app/backend
CMD ["python", "/app/scripts/test-backend.py"]

FROM base AS runtime
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
