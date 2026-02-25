# User Service Dockerfile
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
COPY user-db-access-service/requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.txt

# Copy shared library and application code
COPY shared /app/shared
COPY user-db-access-service/app /app/app
COPY user-db-access-service/tests /app/tests
COPY user-db-access-service/pytest.ini .
COPY user-db-access-service/.coveragerc .

# Non-root user for security
RUN useradd --create-home --shell /bin/bash appuser && \
    chown -R appuser:appuser /app
USER appuser

# Expose port
EXPOSE 8001

# Run the application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]
