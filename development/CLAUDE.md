# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Build & Run

```bash
# Full stack (11 services via Docker Compose)
cp .env.example .env
docker-compose up -d --build        # http://localhost:8088 (default)

# Local dev — start only infrastructure, run one service natively
docker-compose up -d db redis
cd services/<service-name>
pip install -r requirements.txt
uvicorn app.main:app --port <port> --reload
```

Demo credentials: `owner@demo.com` / `password123`, `employee@demo.com` / `password123`

## Testing

There is no centralised test runner. Tests live inside each service and must be run from the service directory.

```bash
cd services/<service-name>
pytest app/tests/ -v                                    # all tests for this service
pytest app/tests/test_routes.py::test_login -v          # single test
pytest app/tests/ -v --cov=app --cov-report=html        # with coverage
```

CI (GitLab) runs 7 test jobs (one per testable service) with Cobertura coverage reports. Pipeline triggers on merge_requests, main, and develop branches.

## Linting & Formatting

Uses **Ruff** (replaces black + isort + flake8). Configuration in `pyproject.toml`.

```bash
# From project root (not per-service):
ruff check services/             # Lint all service code
ruff check --fix services/       # Auto-fix fixable violations
ruff format services/            # Format all service code
ruff format --check services/    # Check formatting without changing files

# Type checking (informational):
mypy services/ --ignore-missing-imports

# Security scanning:
bandit -r services/ -ll -ii --exclude "*/tests/*"
```

Dev tools are in `requirements-dev.txt` at the project root (not in service requirements.txt).

## Architecture

Monorepo with a **layered microservices** design. All backend services use **FastAPI** (async), **SQLAlchemy 2.0** (asyncpg), and **Pydantic 2.x**.

```
NGINX (80)  ──►  Frontend (8000)  ──►  BL Services  ──►  DB-Access Services  ──►  PostgreSQL
                                           │
                                         Redis (caching + token blacklist)
```

### Service map

| Service                  | Port | Role                                              |
|--------------------------|------|---------------------------------------------------|
| nginx                    | 80   | Reverse proxy, rate limiting, security headers     |
| frontend                 | 8000 | Jinja2 + HTMX + Alpine.js + Tailwind (CDN)        |
| user-db-access-service   | 8001 | User/employee CRUD (internal only)                 |
| customer-db-access-service | 8002 | Customer/notes CRUD (internal only)              |
| job-db-access-service    | 8003 | Job/calendar CRUD (internal only)                  |
| user-bl-service          | 8004 | User business logic, role enforcement              |
| auth-service             | 8005 | JWT issue/verify/refresh, token blacklist          |
| job-bl-service           | 8006 | Job scheduling, conflict detection, calendar       |
| customer-bl-service      | 8007 | Customer management, job enrichment                |
| admin-bl-service         | 8008 | Platform admin (superadmin only), org CRUD, audit  |

### Layer responsibilities

- **DB-access services** — pure CRUD, no authentication, no business rules. Blocked from external access by NGINX (403 on `/api/v1/internal/*`).
- **BL services** — validate JWT via auth-service, enforce multi-tenant isolation (`owner_id`), apply business rules, cache reads in Redis with pattern-based invalidation on writes.
- **Frontend** — server-rendered Jinja2 pages. Proxies all `/api/*` requests to the appropriate BL service via `api_proxy.py`. Client-side JWT stored in `localStorage`; `authFetch()` in `main.js` auto-injects the Bearer token.

### Shared module (`services/shared/common/`)

Imported by every backend service:

| File             | Purpose                                                |
|------------------|--------------------------------------------------------|
| `config.py`      | Pydantic `Settings` — service URLs, cache TTLs, secrets (loaded from env / `.env`) |
| `database.py`    | Async SQLAlchemy engine + session factory (`get_async_db` dependency) |
| `redis.py`       | Async Redis client, `cache_get`/`cache_set`/`cache_delete`/`cache_delete_pattern` |
| `exceptions.py`  | `BaseServiceException` hierarchy → auto-mapped to JSON HTTP responses |
| `schemas.py`     | `PaginatedResponse`, `HealthResponse`, `ErrorResponse` |
| `auth.py`        | Shared auth dependencies: `CurrentUser`, `require_role`, `require_superadmin`, `verify_tenant_access` |
| `audit.py`       | Fire-and-forget `log_action()` for immutable audit trail |

## Key Patterns

- **Auth flow**: Login → auth-service issues JWT (HS256, 30 min) + refresh token → BL services verify via `POST /api/v1/auth/verify` → `owner_id` from JWT scopes all queries. Superadmin tokens carry `owner_id=NULL`.
- **Impersonation**: Superadmins can `POST /api/v1/auth/impersonate` to create a 15-min shadow token. The shadow JWT includes `acting_as` and `impersonator_id` claims for audit trail.
- **Field translation**: BL services translate between public field names (`first_name`, `last_name`) and DB field names (`name`) in `service_client.py` via `_to_db_payload` / `_from_db_response`.
- **Inter-service HTTP**: `httpx.AsyncClient` with 10 s timeout. Connection errors raise 503.
- **Database**: PostgreSQL 15, 12 tables with `updated_at` triggers. Schema managed by Alembic migrations via `migration-runner` init-container. Demo data seeded from `scripts/seed-demo-data.sql`.
- **Redis**: DB0 auth, DB1 user-bl, DB2 job-bl, DB3 customer-bl. 128 MB max, LRU eviction, AOF persistence.
- **Frontend interactivity**: HTMX for partial-page swaps (e.g., calendar month navigation), Alpine.js for lightweight state (modals, sidebars). No build step — Tailwind and Alpine loaded from CDN.
