FROM python:3.11-slim

# ---- Environment ----
ENV PYTHONPATH=/app:/app/shared
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# ---- System dependencies ----
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get install -y gcc libpq-dev

# ---- Python dependencies (layer-cached) ----
COPY admin-bl-service/requirements.txt /app/requirements.txt
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r /app/requirements.txt

# ---- Application code ----
COPY shared /app/shared
COPY admin-bl-service/app /app/app

# ---- Non-root user ----
RUN useradd -m appuser && chown -R appuser:appuser /app
USER appuser

# ---- Startup ----
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8008"]
