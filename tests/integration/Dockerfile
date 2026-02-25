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

CMD ["pytest", ".", "-v", "--timeout=30", "--tb=short", "-x", "--junitxml=/tests/results/integration-junit.xml"]
