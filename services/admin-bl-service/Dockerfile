FROM python:3.11-slim

# ---- Environment ----
ENV PYTHONPATH=/app:/app/shared
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# ---- System dependencies ----
RUN apt-get update && apt-get install -y gcc libpq-dev && rm -rf /var/lib/apt/lists/*

# ---- Python dependencies (layer-cached) ----
COPY admin-bl-service/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# ---- Application code ----
COPY shared /app/shared
COPY admin-bl-service/app /app/app

# ---- Non-root user ----
RUN useradd -m appuser && chown -R appuser:appuser /app
USER appuser

# ---- Startup ----
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8008"]
