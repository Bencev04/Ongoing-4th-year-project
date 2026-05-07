# Copilot Instructions — CRM Calendar Platform

> **Auto-loaded by GitHub Copilot Chat.** This file gives Copilot project-specific context so it can generate accurate, idiomatic code for this codebase.

---

## Architecture

Monorepo with **layered microservices**. All backend services use **Python 3.11**, **FastAPI** (async), **SQLAlchemy 2.0** (asyncpg), and **Pydantic 2.x**.

```
NGINX (80)  →  Frontend (8000)  →  BL Services  →  DB-Access Services  →  PostgreSQL 15
                                        │
                                      Redis 7 (caching + token blacklist)
```

### Service Map

| Service                    | Port | Role                                               |
|----------------------------|------|---------------------------------------------------|
| nginx                      | 80   | Reverse proxy, rate limiting, security headers     |
| frontend                   | 8000 | Jinja2 + HTMX + Alpine.js + Tailwind (CDN, no build step) |
| user-db-access-service     | 8001 | User/employee CRUD (internal only)                 |
| customer-db-access-service | 8002 | Customer/notes CRUD (internal only)                |
| job-db-access-service      | 8003 | Job/calendar CRUD (internal only)                  |
| user-bl-service            | 8004 | User business logic, role enforcement              |
| auth-service               | 8005 | JWT issue/verify/refresh, token blacklist          |
| job-bl-service             | 8006 | Job scheduling, conflict detection, calendar       |
| customer-bl-service        | 8007 | Customer management, job enrichment                |
| admin-bl-service           | 8008 | Platform admin (superadmin only), org CRUD, audit  |

### Layer Rules (STRICT — never violate)

- **DB-access services** — pure CRUD, no auth, no business rules. Blocked externally by NGINX.
- **BL services** — validate JWT via HTTP call to auth-service (`POST /api/v1/auth/verify`), enforce `owner_id` tenant isolation, call DB-access services via httpx. **BL services NEVER import SQLAlchemy models or touch the database directly.**
- **Auth-service** — the only service that decodes JWTs. BL services delegate all token validation to auth-service via HTTP — they do NOT share the JWT secret.
- **Frontend** — server-rendered Jinja2 pages. Proxies `/api/*` to BL services via `api_proxy.py`. Client uses `authFetch()` (defined in `base.html`) to auto-inject JWT from `localStorage`.

### Two Request Paths

```
Path A: Browser → NGINX → Frontend API Proxy → BL Service → DB-Access Service
  /api/employees/  (no /v1/) — frontend proxy adds /v1/ and forwards to BL

Path B: Direct API → NGINX → BL Service → DB-Access Service
  /api/v1/employees/  (with /v1/) — NGINX routes directly to BL service
```

---

## Code Style Rules

### Python

- **Type hints REQUIRED** on all function signatures
- **Google-style docstrings** on all public functions/classes
- **Imports**: stdlib → third-party → local (enforced by Ruff `I` rules)
- **Ruff** for formatting: 88 char line length, double quotes, configured in `pyproject.toml`
- **Async/await** for all I/O (database, Redis, HTTP calls) — never use blocking I/O in async functions
- **Naming**: `snake_case` functions, `PascalCase` classes, `UPPER_SNAKE_CASE` constants, `UserCreate`/`UserResponse` schema suffixes
- **Error handling**: Use custom exceptions from `common/exceptions.py` (`NotFoundError`, `ValidationError`, `UnauthorizedError`, `ForbiddenError`, `ConflictError`) — they auto-map to HTTP status codes

### Frontend (JavaScript/Alpine.js)

- **JSDoc type annotations** on all functions
- **Always use `authFetch()`** for authenticated API calls (never plain `fetch()`)
- HTMX for partial-page swaps, Alpine.js for lightweight state

---

## Key Patterns

### Multi-Tenancy

**ALWAYS scope queries by `owner_id`** from the JWT context. Isolation enforced at 3 levels:
1. JWT embeds `owner_id`
2. BL service passes `owner_id` to DB-access service
3. DB-access includes `WHERE owner_id = ?` in every query

```python
# ✅ Always filter by owner_id
users = await db.execute(
    select(User).where(User.owner_id == current_user["owner_id"])
)
# ❌ NEVER query without tenant filter
users = await db.execute(select(User))
```

### Auth Flow

Login → auth-service issues JWT (HS256, 30 min) + refresh token → BL services verify via `POST /api/v1/auth/verify` → `owner_id` from JWT scopes all queries.

JWT payload: `sub` (user_id), `email`, `role`, `owner_id`, `company_id`, `jti`, `exp`, `token_type`.

### Roles (6 levels, numeric hierarchy)

```python
ROLE_HIERARCHY = {
    "superadmin": 100, "owner": 80, "admin": 60,
    "manager": 40, "employee": 20, "viewer": 10,
}
```

Superadmin has `owner_id=NULL` — platform-level, can impersonate any tenant.

### Field Name Translation (BL ↔ DB)

BL services translate between public API names and DB column names in `service_client.py`:

| Public API (BL)         | Database Column (DB-access)    | Service     |
|------------------------|-------------------------------|-------------|
| `assigned_to`          | `assigned_employee_id`         | Job BL      |
| `address`              | `location`                     | Job BL      |
| `first_name` + `last_name` | `name` (concatenated)     | Customer BL |
| `company`              | `company_name`                 | Customer BL |

### Redis Caching

- DB0=auth (blacklist), DB1=user-bl, DB2=job-bl, DB3=customer-bl
- Key pattern: `{domain}:bl:{resource}:{id}` (e.g. `job:bl:job:42`)
- **Redis is optional** — all cache operations silently catch exceptions. App works without Redis.
- On writes: invalidate specific key + pattern-based list cache invalidation

### Inter-Service HTTP

BL services use `httpx.AsyncClient` with 10s timeout. Connection errors raise 503. Service URLs come from `common/config.py` settings (never hardcode).

### Shared Library (`services/shared/common/`)

| File             | Purpose                                                                    |
|------------------|---------------------------------------------------------------------------|
| `config.py`      | Pydantic `BaseSettings` — service URLs, JWT config, cache TTLs, env vars  |
| `database.py`    | Async SQLAlchemy engine + `get_async_db()` dependency                      |
| `redis.py`       | `cache_get`/`cache_set`/`cache_delete`/`cache_delete_pattern`             |
| `exceptions.py`  | Exception hierarchy → auto-mapped to HTTP responses                        |
| `schemas.py`     | `PaginatedResponse`, `HealthResponse`, `ErrorResponse`                     |
| `auth.py`        | `CurrentUser`, `require_role`, `require_superadmin`, `verify_tenant_access`|
| `audit.py`       | Fire-and-forget `log_action()` for immutable audit trail                   |

---

## Database Schema

12 tables, Alembic migrations via `migration-runner` init-container:

```
companies ──1:N──► users ──1:N──► employees
                     │                │
                     │                └──► jobs (assigned_employee_id FK)
                     └──1:N──► customers ──1:N──► customer_notes
                                    │
                                    └──► jobs (customer_id FK)
Auth: refresh_tokens, token_blacklist
Audit: job_history
```

Key facts:
- `users.owner_id` is self-referential FK — owner's `owner_id` = their own `id`
- `jobs.assigned_employee_id` references `employees.id` (NOT `users.id`)
- `jobs.status`: `pending`, `scheduled`, `in_progress`, `completed`, `cancelled`
- `jobs.priority`: `low`, `medium`, `high`, `urgent`
- User deletion is soft-delete (`is_active = FALSE`)
- Roles: `owner`, `admin`, `manager`, `employee`, `viewer` (+ `superadmin` platform-level)

---

## Testing

Tests are **per-service** — run from each service directory:

```bash
cd services/<service-name>
pytest app/tests/ -v                              # all tests
pytest app/tests/test_routes.py::test_login -v    # single test
pytest app/tests/ -v --cov=app --cov-report=html  # with coverage
```

### Test Infrastructure

- **Database**: Async in-memory SQLite (`sqlite+aiosqlite:///:memory:`) — no Postgres needed
- **Redis**: Mocked to raise exceptions — forces DB fallback, tests run without Redis
- **HTTP mocks**: Service-to-service calls mocked at module-level `_http_client`
- **Key fixtures** (from `conftest.py`): `client`, `db_session`, `access_token_for_owner`, `access_token_for_employee`, `sample_users`, `sample_jobs`, `sample_customers`

### Test Naming

```python
def test_get_user_returns_200()
def test_create_job_with_invalid_customer_returns_422()
def test_delete_customer_requires_owner_role()
```

### Browser Tool Selection (Integrated Browser vs Playwright)

- **Use VS Code integrated browser interaction tools first** for quick exploratory checks, manual UI validation, and one-off interactions.
- **Use Playwright** for repeatable, scripted, or multi-step verification where deterministic behavior matters.
- **Escalate from integrated browser to Playwright** when ad-hoc checks need to become reliable automation.
- **Do not force one tool**. Pick the best fit for the current task and switch as needed.

---

## Build & Run Commands

```bash
# Full stack
docker-compose up -d --build        # http://localhost:8088 (default)

# Rebuild single service
docker-compose build <service-name> && docker-compose up -d <service-name>

# Lint/format (from project root)
ruff check services/                # lint
ruff check --fix services/          # auto-fix
ruff format services/               # format
mypy services/ --ignore-missing-imports  # type check
bandit -r services/ -ll -ii --exclude "*/tests/*"  # security scan
```

Demo credentials: `owner@demo.com` / `password123`, `employee@demo.com` / `password123`

---

## Common Pitfalls

- **Don't decode JWTs in BL services** — call auth-service `/api/v1/auth/verify` via HTTP
- **Don't add DB queries to BL services** — call DB-access services via HTTP
- **Don't add auth checks to DB-access services** — all access control is in BL services
- **Don't forget `owner_id` filtering** — every tenant-scoped query MUST include it
- **Don't confuse `assigned_to` (API) with `assigned_employee_id` (DB)** — translation happens in `service_client.py`
- **Don't use plain `fetch()` in frontend** — use `authFetch()` to inject JWT
- **Don't hardcode service URLs** — use `settings.<service>_url` from `common/config.py`
- **Don't assume Redis is available** — all cache operations must be wrapped in try/catch
- **Don't register `/api/jobs/{path}` before `/api/jobs/calendar`** — specific routes go first
- **Don't call `async_init_db()` in BL services** — only DB-access services initialize the DB
- **Don't skip audit logging on admin state changes** — use `common.audit.log_action()`

---

## Key File Locations

| Purpose                          | Location                                           |
|----------------------------------|---------------------------------------------------|
| Service config & URLs            | `services/shared/common/config.py`                 |
| Custom exceptions                | `services/shared/common/exceptions.py`             |
| Shared Pydantic schemas          | `services/shared/common/schemas.py`                |
| Database engine & sessions       | `services/shared/common/database.py`               |
| Redis cache helpers              | `services/shared/common/redis.py`                  |
| Shared auth dependencies         | `services/shared/common/auth.py`                   |
| Audit trail helper               | `services/shared/common/audit.py`                  |
| Database migrations              | `services/shared/migrations/versions/`             |
| Frontend JWT helper              | `services/frontend/app/templates/base.html`        |
| Frontend API proxy routing       | `services/frontend/app/routes/api_proxy.py`        |
| NGINX routing & security         | `services/nginx/nginx.conf`                        |
| Auth token CRUD                  | `services/auth-service/app/crud/auth.py`           |
| Job BL field translation         | `services/job-bl-service/app/service_client.py`    |
| Docker orchestration             | `docker-compose.yml`                               |
| Full architecture docs           | `AGENTS.md`, `CLAUDE.md`, `README.md`             |

---

## Commit Standards

```bash
# Conventional commits, one concern per commit
git commit -m "fix(auth): use authFetch in employees page to include JWT token"
git commit -m "test(frontend): add comprehensive tests for employees page auth"
```
