# CI/CD Pipeline — Setup & Usage Guide

> **Audience:** Any developer who needs to get the CI/CD pipeline running for the first time, or understand how each piece works. Written for `gitlab.comp.dkit.ie`.

---

## Table of Contents

- [Prerequisites](#prerequisites)
- [First-Time Setup (Step by Step)](#first-time-setup-step-by-step)
  - [Step 1 — Push the Pipeline File](#step-1--push-the-pipeline-file)
  - [Step 2 — Set Up a GitLab Runner](#step-2--set-up-a-gitlab-runner)
  - [Step 3 — Set Up SonarQube](#step-3--set-up-sonarqube)
  - [Step 4 — Configure Aikido Security](#step-4--configure-aikido-security)
  - [Step 5 — Configure GitLab CI/CD Variables](#step-5--configure-gitlab-cicd-variables)
  - [Step 6 — Configure Container Registry](#step-6--configure-container-registry)
  - [Step 7 — Configure the Deployment Trigger](#step-7--configure-the-deployment-trigger)
  - [Step 8 — Verify the Pipeline](#step-8--verify-the-pipeline)
- [Pipeline Overview](#pipeline-overview)
- [What Each Stage Does](#what-each-stage-does)
- [Running Things Locally](#running-things-locally)
  - [Unit Tests](#unit-tests)
  - [Integration Tests](#integration-tests)
  - [SonarQube Scan](#sonarqube-scan)
  - [Trivy Security Scan](#trivy-security-scan)
- [Troubleshooting](#troubleshooting)
- [CI/CD Variables Reference](#cicd-variables-reference)
- [File Reference](#file-reference)

---

## Prerequisites

Before starting, make sure you have:

| Requirement | Minimum Version | Check Command |
|-------------|----------------|---------------|
| Docker | 24+ | `docker --version` |
| Docker Compose | v2+ (plugin) | `docker compose version` |
| Git | Any | `git --version` |
| Python | 3.11+ | `python --version` |
| GitLab access | `gitlab.comp.dkit.ie` | Can you open the repo in a browser? |

**Optional (for running scans locally):**

| Tool | Install | Used For |
|------|---------|----------|
| Trivy | [Install guide](https://aquasecurity.github.io/trivy/latest/getting-started/installation/) | Local security scanning |
| sonar-scanner | [Install guide](https://docs.sonarsource.com/sonarqube/latest/analyzing-source-code/scanners/sonarscanner/) | Local code quality analysis |

---

## First-Time Setup (Step by Step)

### Step 1 — Push the Pipeline File

The pipeline is defined in `.gitlab-ci.yml` at the project root. GitLab automatically detects this file and starts running pipelines on every push.

```bash
# Make sure .gitlab-ci.yml is committed
git add .gitlab-ci.yml
git commit -m "ci: add 7-stage CI/CD pipeline"
git push origin iteration-testing
```

Once pushed, go to the repo in GitLab → **CI/CD → Pipelines**. You should see a pipeline appear. If the branch rules match (`main`, `develop`, or a merge request), the first 3 stages will start.

> **First run will be slow** — GitLab needs to pull the Docker images (`python:3.11-slim`, `sonarsource/sonar-scanner-cli`, `aquasec/trivy`). Subsequent runs use cached images and pip packages.

### Step 2 — Set Up a GitLab Runner

The pipeline needs a **GitLab Runner** — a process that actually executes the CI jobs. All jobs in `.gitlab-ci.yml` use the `docker` tag, so the runner must support Docker executors.

**Option A: Use a shared runner (if available)**

Check: GitLab → your project → **Settings → CI/CD → Runners**. If there are shared runners already available and enabled, skip to Step 3.

**Option B: Register your own runner**

If no shared runners are available, you need to register one:

```bash
# 1. Install GitLab Runner on the machine that will run CI jobs
#    (See https://docs.gitlab.com/runner/install/)

# 2. Get the registration token from GitLab:
#    Settings → CI/CD → Runners → "New project runner"
#    Copy the registration token

# 3. Register the runner (interactive)
gitlab-runner register

#    - URL: https://gitlab.comp.dkit.ie/
#    - Registration token: (paste token from GitLab)
#    - Description: crm-calendar-runner
#    - Tags: docker
#    - Executor: docker
#    - Default Docker image: python:3.11-slim

# 4. Start the runner
gitlab-runner start
```

**Important runner configuration:** The runner must support Docker-in-Docker (DinD) for the build and integration test stages. In the runner's `config.toml`, ensure:

```toml
[[runners]]
  [runners.docker]
    privileged = true          # Required for Docker-in-Docker
    volumes = ["/certs/client", "/cache"]
```

Restart the runner after changing `config.toml`:
```bash
gitlab-runner restart
```

### Step 3 — Set Up SonarQube

SonarQube runs as a self-hosted Docker container. You need to set it up **once** and keep it running on a machine accessible from your GitLab Runner.

```bash
# 1. Start SonarQube (from the project root)
docker compose -f ci/docker-compose.sonarqube.yml up -d

# 2. Wait about 60 seconds for it to initialise
#    Check status:
docker compose -f ci/docker-compose.sonarqube.yml logs -f sonarqube
#    Look for: "SonarQube is operational"

# 3. Open the dashboard
#    http://localhost:9000
#    Default login: admin / admin
#    You WILL be prompted to change the password on first login — do it now.

# 4. Create a project
#    - Click "Create Project" → "Manually"
#    - Project display name: CRM Calendar Microservices
#    - Project key: crm-calendar-microservices   (MUST match sonar-project.properties)
#    - Main branch name: main
#    - Click "Set Up"

# 5. Generate an authentication token
#    My Account (top-right avatar) → Security → Tokens
#    - Name: gitlab-ci
#    - Type: Project Analysis Token
#    - Project: CRM Calendar Microservices
#    - Click "Generate" and COPY the token immediately (you won't see it again)

# 6. (Optional) Configure Quality Gate
#    Quality Gates → "Sonar way" (default) is fine to start.
#    You can customise thresholds later (e.g., minimum 80% coverage on new code).
```

**Keep SonarQube running.** The CI pipeline's `sonarqube-analysis` job connects to it every run. If SonarQube is hosted on a different machine from the runner, note the URL (e.g., `http://192.168.1.50:9000`) — you'll need it in Step 4.

> **Note on resources:** SonarQube needs ~2 GB of RAM. If running on a low-spec machine, make sure Docker has enough memory allocated.

### Step 4 — Configure Aikido Security

Aikido Security provides SAST, SCA (dependency scanning), secrets detection, and IaC scanning. It runs at two points in the pipeline: before image builds (source scan) and before deployment (release gate).

```bash
# 1. Sign up / log in at https://app.aikido.dev/

# 2. Connect your GitLab repository
#    Go to Integrations → Add your GitLab repo

# 3. Generate a CI API token
#    Go to CI/CD settings (https://app.aikido.dev/) → Continuous Integration
#    Click "Generate token" and COPY it immediately (you won't see it again)

# 4. (Optional) Configure PR Quality Gating
#    Go to Integrations → PR Quality Gating → Your repo
#    Set severity threshold (e.g., fail on Critical + High)
#    Enable/disable specific scan types (SAST, SCA, secrets, IaC)
```

> **The CI pipeline uses the Aikido CLI** (`@aikidosec/ci-api-client`). It runs as a `node:22` Docker image in GitLab CI, so no local installation is needed.

### Step 5 — Configure GitLab CI/CD Variables

Go to GitLab → your project → **Settings → CI/CD → Variables** and add these:

| Variable | Value | Type | Protected | Masked |
|----------|-------|------|:---------:|:------:|
| `SONAR_HOST_URL` | `http://<sonarqube-host>:9000` | Variable | No | No |
| `SONAR_TOKEN` | The token you generated in Step 3 | Variable | No | **Yes** |
| `AIKIDO_CLIENT_API_KEY` | The token you generated in Step 4 | Variable | No | **Yes** |

> **"Protected" means** the variable is only available on protected branches (like `main`). Set SonarQube and Aikido variables to **not protected** so they work on all branches.

> **"Masked" means** the value is hidden in CI job logs. Always mask tokens and passwords.

> **Aikido API key:** When adding `AIKIDO_CLIENT_API_KEY`, make sure the variable is available on all branches (uncheck "Protect variable") and is masked in logs (check "Mask variable").

### Step 6 — Configure Container Registry

The `build-images` stage pushes Docker images to a container registry. You have two options:

**Option A: GitLab Container Registry (Recommended)**

If your GitLab instance has the Container Registry enabled:

1. Go to your project → **Settings → General → Visibility, project features, permissions**
2. Ensure "Container Registry" is toggled on
3. No extra variables needed — GitLab automatically provides `CI_REGISTRY`, `CI_REGISTRY_USER`, `CI_REGISTRY_PASSWORD`, and `CI_REGISTRY_IMAGE`

**Option B: Docker Hub**

If using Docker Hub instead:

| Variable | Value | Type | Protected | Masked |
|----------|-------|------|:---------:|:------:|
| `CI_REGISTRY` | `docker.io` | Variable | No | No |
| `CI_REGISTRY_USER` | Your Docker Hub username | Variable | No | No |
| `CI_REGISTRY_PASSWORD` | Docker Hub access token | Variable | No | **Yes** |
| `CI_REGISTRY_IMAGE` | `docker.io/<your-username>/crm-calendar` | Variable | No | No |

To create a Docker Hub access token: [hub.docker.com](https://hub.docker.com) → Account Settings → Security → New Access Token.

### Step 7 — Configure the Deployment Trigger

The final `trigger-deploy` stage calls the deployment repository's pipeline via GitLab API. Set this up:

**In the Deployment Repo (`yr4-projectdeploymentrepo`):**

1. Go to **Settings → CI/CD → Pipeline trigger tokens**
2. Click "Add trigger"
3. Description: `dev-repo-trigger`
4. Copy the **trigger token**
5. Note the **trigger URL** (shown on the page — looks like: `https://gitlab.comp.dkit.ie/api/v4/projects/<PROJECT_ID>/trigger/pipeline`)

**Back in the Dev Repo (this repo):**

| Variable | Value | Type | Protected | Masked |
|----------|-------|------|:---------:|:------:|
| `DEPLOY_REPO_TRIGGER_TOKEN` | The trigger token from above | Variable | **Yes** | **Yes** |
| `DEPLOY_REPO_TRIGGER_URL` | The trigger URL from above | Variable | **Yes** | No |

> These are set to **Protected = Yes** because deployment should only happen from `main`.

### Step 8 — Verify the Pipeline

Now test that everything works:

```bash
# 1. Create a feature branch (or use your current branch)
git checkout -b test/verify-pipeline

# 2. Make a small change (e.g., add a comment to any file)
echo "# CI pipeline verification" >> services/auth-service/app/main.py

# 3. Push and create a merge request
git add -A
git commit -m "ci: verify pipeline setup"
git push origin test/verify-pipeline
```

Go to GitLab → **CI/CD → Pipelines**. You should see:

| Stage | Expected Result |
|-------|----------------|
| ✅ `test` | 9 parallel unit test jobs + Trivy code scan |
| ✅ `quality` | SonarQube analysis — quality gate passes |
| ⏭️ `security:code` | Skipped (not `main` branch) |
| ⏭️ `build` | Skipped (not `main` branch) |
| ⏭️ `integration` | Skipped (not `main` branch) |
| ⏭️ `scan:image` | Skipped (not `main` branch) |
| ⏭️ `deploy` | Skipped (not `main` branch) |

Once merged to `main`, all 8 stages will run. The deploy stage will show a ▶️ play button — it requires manual approval.

```bash
# Clean up the test branch
git checkout iteration-testing
git branch -D test/verify-pipeline
git push origin --delete test/verify-pipeline
```

---

## Pipeline Overview

```
Feature/MR branches (~3-5 min):

  ┌─────────────────────────────────────────┐    ┌───────────┐
  │ 1. Unit Tests (9 parallel)              │───▶│ 2. Sonar- │
  │    + Trivy Code Scan (parallel)         │    │   Qube    │
  └─────────────────────────────────────────┘    └───────────┘
  ✅ Done — fast feedback for developers

main branch — full pipeline (~12-16 min):

  ┌──────┐  ┌──────┐  ┌────────┐  ┌──────┐  ┌──────┐  ┌──────────────┐  ┌──────────┐
  │ Unit │─▶│Sonar │─▶│Aikido  │─▶│Build │─▶│Integ │─▶│Trivy Image + │─▶│  Deploy  │
  │Tests │  │ Qube │  │Source  │  │Images│  │Tests │  │Aikido Release│  │ (manual) │
  │+Trivy│  │      │  │  Scan  │  │      │  │(pre- │  │    (parallel)│  │          │
  │ Code │  │      │  │        │  │      │  │built)│  │              │  │          │
  └──────┘  └──────┘  └────────┘  └──────┘  └──────┘  └──────────────┘  └──────────┘
```

### Branch Rules

| Branch / Event | Stages That Run |
|----------------|----------------|
| Any **merge request** | 1 (test) → 2 (quality) |
| Push to **`develop`** | 1 (test) → 2 (quality) |
| Push to **`main`** | All 8 stages |
| Any other branch | Nothing (pipeline not triggered) |

---

## What Each Stage Does

### Stage 1 — Unit Tests

Runs 8 parallel pytest jobs, one per service:

| Job Name | Service | Uses Postgres? |
|----------|---------|:--------------:|
| `test:auth-service` | Auth | No (in-memory SQLite) |
| `test:user-db-access-service` | User DB Access | Yes (CI service container) |
| `test:customer-db-access-service` | Customer DB Access | Yes (CI service container) |
| `test:job-db-access-service` | Job DB Access | Yes (CI service container) |
| `test:user-bl-service` | User BL | No (HTTP mocked) |
| `test:customer-bl-service` | Customer BL | No (HTTP mocked) |
| `test:job-bl-service` | Job BL | No (HTTP mocked) |
| `test:frontend` | Frontend | No (HTTP mocked) |

Each job produces a `coverage.xml` (Cobertura format) passed as an artifact to Stage 2.

### Stage 2 — SonarQube Quality

Uses the `sonarsource/sonar-scanner-cli` image. Reads `sonar-project.properties` and sends code + coverage reports to your SonarQube server. Waits for the quality gate verdict before passing/failing.

### Stage 3 — Aikido Source Scan (main only)

Uses the Aikido CLI (`@aikidosec/ci-api-client`) on a `node:22` image. Scans source code for SAST vulnerabilities, dependency CVEs (SCA), hardcoded secrets, and IaC misconfigurations. Runs **before** building Docker images to catch security issues early and avoid wasting CI minutes on vulnerable code.

### Stage 4 — Build Images (main only)

Uses Docker-in-Docker. Builds all 10 Dockerfiles, tags with commit SHA + `:latest`, pushes to the container registry.

### Stage 5 — Integration Tests (main only)

Pulls **pre-built images** from the build stage (via `ci/docker-compose.ci-prebuilt.yml`) instead of building from scratch. This eliminates the double-build problem and speeds up integration tests by ~3-4 minutes. Only the integration-runner container is built from scratch (it's not in the registry).

### Stage 6a — Trivy Image Scan (main only)

Pulls each built image and scans it for OS-level vulnerabilities. Runs in parallel with the Aikido release gate for defence in depth.

### Stage 6b — Aikido Release Gate (main only)

Final security gate before deployment. Uses the Aikido CLI to scan the release and block deployment if new critical/high issues are detected. Runs in parallel with the Trivy image scan — different vulnerability databases provide broader coverage.

### Stage 7 — Deploy (main only, manual)

Requires a human to click the ▶️ play button. Only triggers after both security scans (Trivy + Aikido) and integration tests pass. Sends a `curl` POST to the deployment repo's trigger URL, passing the image tag and commit SHA.

---

## Running Things Locally

You don't need to wait for CI to test things. Here's how to run each piece on your machine.

### Unit Tests

```bash
# All services at once (uses helper script)
./scripts/test-all.sh
# or on Windows:
powershell -File scripts/run-all-tests.ps1

# Single service
cd services/auth-service
pip install -r requirements.txt
pytest app/tests/ -v

# With coverage report
pytest app/tests/ -v --cov=app --cov-report=html
# Open htmlcov/index.html in your browser
```

### Integration Tests

Integration tests require the full Docker Compose stack to be running.

```bash
# 1. Start the application stack
docker compose up -d --build

# 2. Wait for all services to be healthy (~30-60 seconds)
docker compose ps
# All services should show "healthy"

# 3. Install test dependencies
cd tests/integration
pip install -r requirements.txt

# 4. Run the tests (pointing at localhost since you're outside Docker)
INTEGRATION_BASE_URL=http://localhost pytest . -v

# On Windows (PowerShell):
$env:INTEGRATION_BASE_URL = "http://localhost"
pytest . -v

# 5. (Optional) Run a single test file
INTEGRATION_BASE_URL=http://localhost pytest test_auth_flow.py -v

# 6. Stop the stack when done
cd ../..
docker compose down
```

**Alternative — run tests using the CI compose override (same as CI does):**

```bash
# This runs the integration-runner container inside the Docker network
docker compose -f docker-compose.yml -f ci/docker-compose.ci.yml up -d --build
docker compose -f docker-compose.yml -f ci/docker-compose.ci.yml run --rm integration-runner
docker compose -f docker-compose.yml -f ci/docker-compose.ci.yml down -v
```

### SonarQube Scan

```bash
# 1. Start SonarQube (if not already running)
docker compose -f ci/docker-compose.sonarqube.yml up -d

# 2. Wait for it to be ready (~60 seconds)
#    Check: http://localhost:9000

# 3. Run unit tests first (to generate coverage.xml files)
./scripts/test-all.sh

# 4. Run the scanner
sonar-scanner \
  -Dsonar.host.url=http://localhost:9000 \
  -Dsonar.token=YOUR_TOKEN_HERE \
  -Dproject.settings=ci/sonar-project.properties

# 5. View results at http://localhost:9000/dashboard?id=crm-calendar-microservices
```

### Trivy Security Scan

```bash
# Scan Python dependencies (same as CI Stage 3)
trivy fs --severity CRITICAL,HIGH ./services/

# Scan a specific Docker image (same as CI Stage 5)
docker compose build auth-service
trivy image crm_auth_service:latest

# Generate JSON report
trivy fs --severity HIGH,CRITICAL --format json --output report.json ./services/
```

---

## Troubleshooting

### Pipeline doesn't start

| Symptom | Fix |
|---------|-----|
| "This project is not currently set up to use CI/CD" | Push `.gitlab-ci.yml` to the repo. GitLab auto-detects it. |
| Pipeline created but jobs are "pending" forever | No runner available. Check Settings → CI/CD → Runners. Register one (see Step 2). |
| "This job is stuck because the project doesn't have any runners online assigned to it" | Same as above — register a runner with the `docker` tag. |

### Unit tests fail

| Symptom | Fix |
|---------|-----|
| `ModuleNotFoundError` | The `pip install -r requirements.txt` step is likely failing. Check the job log for pip errors. |
| DB-access test fails with connection error | Postgres service container might not be ready. Add `sleep 5` before pytest if needed. |
| `pytest-xdist` not found (`-n auto` fails) | Add `pytest-xdist` to the service's `requirements.txt`. |

### SonarQube stage fails

| Symptom | Fix |
|---------|-----|
| "Not authorized" / 401 | `SONAR_TOKEN` is wrong or expired. Generate a new one in SonarQube dashboard. |
| "Project not found" | `sonar.projectKey` in `ci/sonar-project.properties` must match the project key in SonarQube. It should be `crm-calendar-microservices`. |
| "Quality Gate FAILED" | This is intentional — fix the issues shown in the SonarQube dashboard. Common: insufficient coverage on new code, code smells, bugs. |
| Connection refused | SonarQube is not running, or `SONAR_HOST_URL` points to the wrong address. The runner must be able to reach SonarQube over the network. |

### Trivy stage fails

| Symptom | Fix |
|---------|-----|
| "CRITICAL vulnerability found" (exit code 1) | A Python dependency has a known CRITICAL CVE. Update the dependency: `pip install --upgrade <package>` and update `requirements.txt`. |
| Scan takes too long / times out | Add `--timeout 15m` to the trivy command, or check if `ci/.trivy.yaml` has `timeout` set too low. |

### Build stage fails

| Symptom | Fix |
|---------|-----|
| "Cannot connect to the Docker daemon" | The runner doesn't support Docker-in-Docker. Set `privileged = true` in `config.toml` (see Step 2). |
| "denied: access forbidden" on push | Container registry credentials are wrong. Check `CI_REGISTRY_USER` / `CI_REGISTRY_PASSWORD`. For GitLab CR, these are auto-provided. |
| Dockerfile build error | Fix the Dockerfile locally first: `docker compose build <service-name>`. |

### Integration tests fail

| Symptom | Fix |
|---------|-----|
| "Cannot connect to http://nginx-gateway" | Services aren't healthy yet. Increase the wait timeout in the CI job (currently 120s). |
| Login fails (401/500) | The database might not have seed data. Check that `scripts/init-db.sql` runs during `docker compose up`. |
| Tests pass locally but fail in CI | CI uses `ci/docker-compose.ci.yml` overrides. Check the environment variables there match what the app expects. |

### Deploy stage

| Symptom | Fix |
|---------|-----|
| "HTTP 401" on curl trigger | `DEPLOY_REPO_TRIGGER_TOKEN` is wrong. Regenerate it in the deployment repo. |
| "HTTP 404" on curl trigger | `DEPLOY_REPO_TRIGGER_URL` is wrong. Check the project ID in the URL matches the deployment repo. |
| Nothing happens after clicking ▶️ | Check the deployment repo → CI/CD → Pipelines. The triggered pipeline runs there, not here. |

---

## CI/CD Variables Reference

Complete list of all variables used by the pipeline:

| Variable | Required | Where to Set | Default | Purpose |
|----------|:--------:|-------------|---------|---------|
| `SONAR_HOST_URL` | ✅ | GitLab CI/CD Variables | — | URL of your SonarQube instance |
| `SONAR_TOKEN` | ✅ | GitLab CI/CD Variables (masked) | — | SonarQube auth token |
| `CI_REGISTRY` | ✅ | Auto (GitLab CR) or manual | — | Container registry hostname |
| `CI_REGISTRY_USER` | ✅ | Auto (GitLab CR) or manual | — | Registry login username |
| `CI_REGISTRY_PASSWORD` | ✅ | Auto (GitLab CR) or manual | — | Registry login password |
| `CI_REGISTRY_IMAGE` | ✅ | Auto (GitLab CR) or manual | — | Base image path (e.g., `registry.example.com/group/project`) |
| `AIKIDO_CLIENT_API_KEY` | ✅ | GitLab CI/CD Variables (masked) | — | Aikido Security CI API token |
| `DEPLOY_REPO_TRIGGER_TOKEN` | For deploy | GitLab CI/CD Variables (masked, protected) | — | Pipeline trigger token for deployment repo |
| `DEPLOY_REPO_TRIGGER_URL` | For deploy | GitLab CI/CD Variables (protected) | — | API URL to trigger deployment repo |
| `DOCKER_DRIVER` | No | `.gitlab-ci.yml` | `overlay2` | Docker storage driver |
| `PIP_CACHE_DIR` | No | `.gitlab-ci.yml` | `$CI_PROJECT_DIR/.cache/pip` | Pip cache location for faster installs |

---

## File Reference

| File | What It Does |
|------|-------------|
| `.gitlab-ci.yml` | The pipeline definition — 8 stages, all job configurations, rules |
| `docker-compose.yml` | Main application stack (11 services + Postgres + Redis) |
| `ci/docker-compose.ci.yml` | CI overrides — removes ports, pins env vars, adds integration-runner |
| `ci/docker-compose.ci-prebuilt.yml` | Pre-built image overrides — maps services to registry images for integration tests |
| `ci/docker-compose.sonarqube.yml` | SonarQube + its own Postgres (separate from the app) |
| `ci/sonar-project.properties` | SonarQube scanner config — project key, sources, exclusions, coverage paths |
| `ci/.trivy.yaml` | Trivy scanner config — severity policy, skip-dirs, timeout |
| `.gitignore` | Keeps build artifacts, caches, and secrets out of Git |
| `services/.dockerignore` | Keeps tests, caches, and IDE files out of Docker images |
| `tests/integration/conftest.py` | Integration test fixtures — HTTP client, auth tokens, health check |
| `tests/integration/requirements.txt` | Python deps for integration tests (httpx, pytest, pytest-timeout) |
| `tests/integration/test_auth_flow.py` | Login, verify, refresh, logout flow tests |
| `tests/integration/test_user_flow.py` | User and employee listing tests |
| `tests/integration/test_customer_flow.py` | Customer CRUD + notes tests |
| `tests/integration/test_job_flow.py` | Job CRUD, calendar, queue tests |
| `tests/integration/test_e2e_smoke.py` | Health checks, full business path, NGINX routing |

---

**Last Updated:** February 2026
