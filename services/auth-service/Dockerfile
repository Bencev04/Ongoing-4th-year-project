# Auth Service Dockerfile
# Handles authentication, JWT tokens, and tenant isolation

FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app:/app/shared

# Install system dependencies (gcc + libpq-dev needed for asyncpg C extension)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies first (best layer caching)
COPY auth-service/requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.txt

# Copy shared library and application code
COPY shared /app/shared
COPY auth-service/app /app/app
COPY auth-service/pytest.ini .
COPY auth-service/.coveragerc .

# Create non-root user for security
RUN useradd --create-home --shell /bin/bash appuser && \
    chown -R appuser:appuser /app
USER appuser

# Expose port
EXPOSE 8005

# Health check (Python stdlib — no curl dependency)
HEALTHCHECK --interval=5s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8005/api/v1/health')"

# Run the application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8005"]
