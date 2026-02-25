# Customer Service (Business Logic) Dockerfile
# Handles tenant-isolated customer CRUD, notes, and data enrichment

FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app:/app/shared

# Install Python dependencies first (best layer caching)
COPY customer-bl-service/requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.txt

# Copy shared library and application code
COPY shared /app/shared
COPY customer-bl-service/app /app/app

# Non-root user for security
RUN useradd --create-home --shell /bin/bash appuser && \
    chown -R appuser:appuser /app
USER appuser

EXPOSE 8007

# Health check (Python stdlib — no curl dependency)
HEALTHCHECK --interval=5s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8007/api/v1/health')"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8007"]
