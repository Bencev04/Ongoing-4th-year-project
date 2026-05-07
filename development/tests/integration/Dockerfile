# ==============================================================================
# Integration Test Runner — Dockerfile
#
# Copies tests into the image so CI (DinD) doesn't need bind mounts.
# ==============================================================================

FROM python:3.11-slim

WORKDIR /tests

# Install dependencies first (cached layer)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy test files
COPY . .

CMD ["pytest", ".", "-v", "--timeout=120", "--tb=short", "--junitxml=/tests/results/integration-junit.xml"]
