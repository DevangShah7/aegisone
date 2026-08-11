# Dev container Dockerfile. Multi-stage, non-root, no shell.
# Build from backend/: `docker build -t aegisone-backend:dev .`
# Run from repo root:    `docker compose -f infra/docker-compose.yml up backend`

# ---- builder ----
FROM python:3.12-slim AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /build

RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential \
 && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./

RUN pip install --prefix=/install .

# ---- runtime ----
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/usr/local/bin:${PATH}"

# Run as a non-root user.
RUN groupadd --system --gid 1000 aegisone \
 && useradd  --system --uid 1000 --gid aegisone --create-home --shell /sbin/nologin aegisone

WORKDIR /app

COPY --from=builder /install /usr/local
COPY --from=builder /build/app ./app
COPY --from=builder /build/alembic ./alembic
COPY --from=builder /build/alembic.ini ./

USER aegisone

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,sys; urllib.request.urlopen('http://localhost:8000/healthz', timeout=2); sys.exit(0)" \
    || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
