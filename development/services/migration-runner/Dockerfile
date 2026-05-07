# Alembic Migration Runner
#
# Lightweight init-container that runs `alembic upgrade head` against
# the shared PostgreSQL database before any application service starts.
# Build context is ./services (same as other service Dockerfiles).

FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app:/app/shared

# System deps for psycopg2
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev

# Install Python deps (alembic, psycopg2-binary, sqlalchemy, pydantic-settings)
COPY migration-runner/requirements.txt /app/requirements.txt
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.txt

# Copy the shared library (common/ + alembic.ini + migrations/)
COPY shared /app/shared

# Copy model files from each DB-access service under distinct paths
# so all_models.py can import them without package-name collisions.
COPY auth-service/app            /app/app_auth
COPY user-db-access-service/app  /app/app_user
COPY customer-db-access-service/app /app/app_customer
COPY job-db-access-service/app   /app/app_job

# Ensure each copied app directory is a package
RUN touch /app/app_auth/__init__.py \
          /app/app_user/__init__.py \
          /app/app_customer/__init__.py \
          /app/app_job/__init__.py

# Copy the entrypoint script
COPY migration-runner/run_migrations.py /app/run_migrations.py

# Copy seed file if present in build context.
# The sq[l] wildcard makes this a no-op if the file is absent.
# CI copies scripts/seed-demo-data.sql into services/migration-runner/ before build.
COPY migration-runner/seed-demo-data.sq[l] /app/

WORKDIR /app/shared

# Run migrations (and optional seed) on container start
CMD ["python", "/app/run_migrations.py"]
