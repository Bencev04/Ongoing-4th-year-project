# AGENTS.md — Development Guidelines for AI Coding Agents

This file provides standardized guidelines for AI coding agents working in this repository. Follow these conventions to maintain code quality, consistency, and industry best practices.

> **Living Document**: This file should be updated whenever architectural decisions, patterns, or conventions change. Update it in the same commit as the changes it documents. Review quarterly to ensure accuracy and relevance.

---

## Build, Test & Run Commands

### Docker Environment (Primary)

```bash
# Full stack startup
docker-compose up -d --build

# Rebuild single service after code changes
docker-compose build <service-name> && docker-compose up -d <service-name>

# View service logs
docker-compose logs -f <service-name>

# Stop all services
docker-compose down
```

### Testing

**IMPORTANT:** Tests are per-service, not centralized. This follows microservices best practices.

#### Quick Test Commands (Recommended)

```bash
# Run all tests across all services
make test
# Or: ./scripts/test-all.sh

# Run tests for specific service
make test-frontend
make test-job-bl
# Or: ./scripts/test-all.sh --service frontend

# Run with detailed output
./scripts/test-all.sh --verbose

# View all available commands
make help
```

#### Manual Testing (Per-Service)

```bash
# Run all tests for a service
cd services/<service-name>
pytest app/tests/ -v

# Run a single test file
pytest app/tests/test_routes.py -v

# Run a single test function
pytest app/tests/test_routes.py::test_login -v

# Run a single test class
pytest app/tests/test_routes.py::TestAuthRoutes -v

# Run with coverage report
pytest app/tests/ -v --cov=app --cov-report=html

# Run tests inside Docker container
docker-compose exec <service-name> pytest app/tests/ -v
```

**Test Execution Example:**
```bash
# Testing frontend employees page
cd services/frontend
pytest app/tests/test_employees.py::TestEmployeesPage::test_employees_page_loads -v
```

**Why Per-Service Tests?**
- ✅ Service independence - Test, deploy, version independently
- ✅ Faster CI/CD - Only test services that changed
- ✅ Clear ownership - Tests live with the code they test
- ✅ Isolated dependencies - Each service has its own test requirements
- ❌ **Don't centralize tests** - This breaks microservice principles

### Local Development

```bash
# Start infrastructure only
docker-compose up -d db redis

# Run service locally with hot-reload
cd services/<service-name>
pip install -r requirements.txt
uvicorn app.main:app --port <port> --reload
```

### Linting & Formatting

```bash
# Run from service directory
black .              # Code formatter
isort .              # Import sorter
mypy .               # Type checker
```

---

## Code Style Guidelines

### Python Backend Services

#### Imports

**Order:** Standard library → Third-party → Local imports (use `isort` to maintain)

```python
# Standard library
import sys
from datetime import datetime
from typing import Optional, Dict, Any, List

# Third-party
import httpx
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession

# Local application
from app.models import User
from app.schemas import UserResponse
from common.config import settings
from common.exceptions import NotFoundError
```

#### Type Hints

**REQUIRED on all function signatures:**

```python
# ✅ GOOD - Full type hints
async def get_user(
    user_id: int,
    db: AsyncSession,
    current_user: Dict[str, Any]
) -> UserResponse:
    """Get user by ID with tenant isolation."""
    ...

# ❌ BAD - Missing type hints
async def get_user(user_id, db, current_user):
    ...
```

**Use `Optional` for nullable values:**

```python
# ✅ GOOD
def process_customer(
    name: str,
    email: Optional[str] = None,
    phone: Optional[str] = None
) -> Dict[str, Any]:
    ...

# ❌ BAD - No indication of nullability
def process_customer(name: str, email=None, phone=None):
    ...
```

#### Documentation

**Docstrings required for:**
- All public functions/methods
- All classes
- Complex logic blocks

**Format:** Google-style docstrings

```python
def create_job(
    job_data: Dict[str, Any],
    db: AsyncSession,
    current_user: Dict[str, Any]
) -> Job:
    """
    Create a new job with tenant isolation.
    
    Args:
        job_data: Job creation payload with title, customer_id, etc.
        db: Database session for async operations.
        current_user: Authenticated user context from JWT.
        
    Returns:
        Created job instance with generated ID.
        
    Raises:
        ValidationError: If customer_id doesn't belong to user's tenant.
        DatabaseError: If job creation fails.
    """
    ...
```

#### Naming Conventions

| Type | Convention | Example |
|------|------------|---------|
| **Functions** | `snake_case` | `get_user_by_id`, `validate_token` |
| **Classes** | `PascalCase` | `UserService`, `AuthMiddleware` |
| **Constants** | `UPPER_SNAKE_CASE` | `MAX_RETRIES`, `DEFAULT_TTL` |
| **Private** | Prefix with `_` | `_validate_internal`, `_cache_key` |
| **Database models** | Singular `PascalCase` | `User`, `Customer`, `Job` |
| **Pydantic schemas** | Suffix with purpose | `UserCreate`, `UserResponse`, `JobUpdate` |

#### Error Handling

**Use custom exceptions from `common/exceptions.py`:**

```python
# ✅ GOOD - Structured exceptions
from common.exceptions import NotFoundError, UnauthorizedError, ValidationError

if not user:
    raise NotFoundError(
        message="User not found",
        resource_type="user",
        resource_id=user_id
    )

if user.owner_id != current_user["owner_id"]:
    raise UnauthorizedError("Access denied: tenant mismatch")

# ❌ BAD - Generic exceptions
if not user:
    raise Exception("User not found")
```

**HTTP exception mapping (FastAPI):**

```python
# Exceptions auto-convert to JSON responses
# NotFoundError → 404
# ValidationError → 422
# UnauthorizedError → 401
# ForbiddenError → 403
# ConflictError → 409
```

#### Async/Await Patterns

**Always use async for I/O operations:**

```python
# ✅ GOOD - Async database & HTTP calls
async def enrich_job(job_id: int) -> Dict[str, Any]:
    job = await db.get(Job, job_id)
    customer = await get_customer(job.customer_id)
    return {**job.dict(), "customer": customer}

# ❌ BAD - Blocking I/O in async function
async def get_user(user_id: int) -> User:
    return db.query(User).get(user_id)  # Blocking!
```

---

### Frontend (JavaScript/Alpine.js)

#### JSDoc Type Annotations

**REQUIRED for all functions and variables:**

```javascript
/**
 * Load all employees from the backend API.
 * Uses authFetch to automatically inject JWT authentication token.
 * 
 * @returns {Promise<void>}
 * @throws {Error} If authentication fails or server returns error
 */
async loadEmployees() {
    /** @type {Array<Object>} */
    this.employees = [];
    ...
}
```

#### Authentication

**ALWAYS use `authFetch()` for authenticated API calls:**

```javascript
// ✅ GOOD - Uses authFetch helper (auto-injects JWT)
const response = await authFetch('/api/employees/', {
    method: 'GET',
    headers: { 'Content-Type': 'application/json' }
});

// ❌ BAD - Plain fetch (missing auth token)
const response = await fetch('/api/employees/');
```

**Location:** `authFetch()` is defined in `base.html` (lines 306-329)

#### Error Handling

```javascript
// ✅ GOOD - Comprehensive error handling
try {
    const resp = await authFetch('/api/employees/');
    
    if (resp.status === 401) {
        throw new Error('Missing authentication credentials');
    }
    if (resp.status === 403) {
        throw new Error('Permission denied');
    }
    if (!resp.ok) {
        const data = await resp.json().catch(() => null);
        throw new Error(data?.detail || `Server error (${resp.status})`);
    }
    
    return await resp.json();
} catch (err) {
    console.error('Failed to load employees:', err);
    this.error = err.message || 'Failed to load data';
}
```

---

## Testing Standards

### Test Infrastructure

Every service uses the same test setup pattern — study `conftest.py` before writing tests:

**Database:** Async in-memory SQLite (`sqlite+aiosqlite:///:memory:` with `StaticPool`). Tables are created before each test, dropped after. No real Postgres needed.

**Redis mock:** Auto-use fixture patches `get_redis` to raise `Exception` — forces Postgres fallback path. Tests run without Redis.

**HTTP mocks:** Service-to-service calls are mocked at the module-level `_http_client` variable. For auth-service tests, the mock returns `{"authenticated": True, ...}` by default. For frontend tests, the mock raises `httpx.ConnectError`.

**Client types:**
- Auth service / DB-access: `AsyncClient` via `ASGITransport(app=app)` — async tests with `@pytest.mark.asyncio`
- Frontend: Sync `TestClient` for HTML rendering tests, `AsyncClient` available for async tests

**Key fixtures available in most services:**
```python
# From conftest.py — use these, don't recreate them
client          # TestClient or AsyncClient
db_session      # AsyncSession (in-memory SQLite)
access_token_for_owner    # Valid JWT for owner role
access_token_for_employee # Valid JWT for employee role
sample_users    # List of dict with user data (frontend)
sample_jobs     # List of dict with job data (frontend)
sample_customers # List of dict with customer data (frontend)
```

### Test File Structure

```python
"""
Module description.

Test coverage for [component/feature].
"""

import pytest
from fastapi.testclient import TestClient


class TestFeatureName:
    """Test suite for [feature] functionality."""
    
    def test_specific_behavior(self, client: TestClient) -> None:
        """
        Test that [specific behavior] works correctly.
        
        Verifies:
        - [Assertion 1]
        - [Assertion 2]
        """
        response = client.get("/endpoint")
        assert response.status_code == 200
        assert "expected" in response.text
```

### Test Naming

```python
# Format: test_<action>_<expected_result>
def test_get_user_returns_200()
def test_create_job_with_invalid_customer_returns_422()
def test_delete_customer_requires_owner_role()
def test_employees_page_uses_authfetch()  # Frontend tests
```

### Fixtures

Use fixtures from `conftest.py` - don't duplicate setup:

```python
# Available fixtures (see services/<service>/app/tests/conftest.py)
def test_example(client: TestClient, sample_users: List[Dict]) -> None:
    """Use provided fixtures - don't create new ones."""
    ...
```

---

## Architecture Patterns

### How Requests Flow (Two Proxy Layers)

There are **two routing paths** through the system — understand both to avoid misrouting:

```
Path A: Browser → NGINX → Frontend API Proxy → BL Service → DB-Access Service
  /api/employees/  (no /v1/) — frontend proxy adds /v1/ and forwards to BL

Path B: Direct API → NGINX → BL Service → DB-Access Service
  /api/v1/employees/  (with /v1/) — NGINX routes directly to BL service
```

The frontend proxy (`services/frontend/app/routes/api_proxy.py`) maps browser-friendly routes:
```
/api/auth/*       → auth-service:8005
/api/users/*      → user-bl-service:8004
/api/employees/*  → user-bl-service:8004
/api/customers/*  → customer-bl-service:8007
/api/notes/*      → customer-bl-service:8007
/api/jobs/*       → job-bl-service:8006
```

**Gotcha:** `/api/jobs/calendar` and `/api/jobs/queue` are registered as specific routes **before** the catch-all `/api/jobs/{path:path}` — order matters.

### Service Communication Pattern

```
BL services NEVER touch the database directly.
DB-access services NEVER perform auth checks.

Every BL endpoint:
  1. Extract Bearer token from request
  2. POST token to auth-service:8005/api/v1/auth/verify (HTTP call, not local decode)
  3. Auth service returns { valid: true/false, user_id, owner_id, role }
  4. BL service enforces tenant isolation using owner_id
  5. BL service calls DB-access service for CRUD
  6. BL service translates field names and enriches response
```

**Key detail:** BL services delegate token validation entirely to the auth service via HTTP — they do NOT decode JWTs locally and do NOT share the JWT secret. This adds a network hop per request but provides security isolation.

### Auth Service → User DB Access Dependency

The auth service is special — it calls `user-db-access-service` directly (not through a BL layer):
- **Login:** `POST user-db-access:8001/api/v1/internal/authenticate` to verify credentials
- **Refresh:** `GET user-db-access:8001/api/v1/users/{id}` to fetch fresh claims for new JWT
- **Verify endpoint** returns `{ valid: true/false }` — never raises HTTP errors, so callers check the response body

### Multi-Tenancy

**ALWAYS scope queries by `owner_id`:**

```python
# ✅ GOOD - Tenant-isolated query
users = await db.execute(
    select(User).where(
        User.owner_id == current_user["owner_id"],
        User.is_active == True
    )
)

# ❌ BAD - Missing tenant isolation (security vulnerability!)
users = await db.execute(select(User))
```

**Isolation is enforced at THREE levels:**
1. JWT embeds `owner_id` → extracted by BL service
2. BL service passes `owner_id` as query param to DB-access service
3. DB-access service includes `WHERE owner_id = ?` in every SQL query

**No tenant isolation at the DB-access layer itself** — it's a raw CRUD service. Protection comes from NGINX blocking `/api/v1/internal/*` and the BL layer always filtering by `owner_id`.

### Field Name Translation (BL Services)

BL services translate between public API names and internal DB column names. Translation happens in `service_client.py` via `_to_db_payload()` and `_from_db_response()`:

| Public API (BL) | Database Column (DB-access) | Service |
|-----------------|----------------------------|---------|
| `assigned_to` | `assigned_employee_id` | Job BL |
| `address` | `location` | Job BL |
| `first_name` + `last_name` | `name` (concatenated) | Customer BL |
| `company` | `company_name` | Customer BL |

**Gotcha:** `assigned_employee_id` references `employees.id` (not `users.id`). The BL layer's `assigned_to` field maps to this.

### Redis Caching

```python
# Pattern: cache_get → if miss → fetch from DB → cache_set
cache_key = f"user:bl:user:{user_id}"
cached = await cache_get(cache_key)

if cached:
    return cached

user = await fetch_from_db(user_id)
await cache_set(cache_key, user, ttl=settings.cache_ttl_medium)
return user

# On write operations: invalidate cache
await cache_delete(cache_key)
await cache_delete_pattern("user:bl:users:*")  # Wipe list caches
```

**Redis DB allocation** (each BL service uses a separate Redis database):

| Redis DB | Service | What It Caches |
|----------|---------|----------------|
| DB 0 | Auth Service | Token blacklist (jti → expiry) |
| DB 1 | User BL | User/employee response caching |
| DB 2 | Job BL | Job, calendar, queue response caching |
| DB 3 | Customer BL | Customer/note response caching |

**Cache key prefixes:** `{domain}:bl:{resource}:{id}` — e.g. `job:bl:job:42`, `job:bl:calendar:2026-02`

**Redis is optional:** All cache operations silently catch exceptions and log at DEBUG. Auth blacklist falls back to Postgres. Cache misses just result in DB calls. The app functions correctly without Redis.

### Shared Library (`services/shared/common/`)

Every service imports from the shared library using a `sys.path.insert` hack:
```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "shared"))
from common.config import settings
```

Dockerfiles set `PYTHONPATH=/app:/app/shared` as a fallback.

| File | What It Provides |
|------|-----------------|
| `config.py` | Pydantic `BaseSettings` singleton — all service URLs, JWT config, cache TTLs, overridable via env vars |
| `database.py` | Async SQLAlchemy engine + `get_async_db()` / `get_db()` dependency generators, `async_init_db()` startup hook |
| `redis.py` | `cache_get()`, `cache_set()`, `cache_delete()`, `cache_delete_pattern()` — all resilient to failures |
| `exceptions.py` | `NotFoundError` (404), `ValidationError` (422), `UnauthorizedError` (401), `ForbiddenError` (403), `ConflictError` (409), `DatabaseError` (500) |
| `schemas.py` | `BaseSchema`, `TimestampMixin`, `PaginatedResponse[T]`, `HealthResponse`, `ErrorResponse`, `SuccessResponse` |

### Database Schema

9 tables defined in `scripts/init-db.sql`. Key relationships:

```
companies ──1:N──► users ──1:N──► employees
                     │                │
                     │                └──► jobs (assigned_employee_id FK)
                     │
                     └──1:N──► customers ──1:N──► customer_notes
                                    │
                                    └──► jobs (customer_id FK)

Auth tables: refresh_tokens, token_blacklist
Audit: job_history (auto-logged changes)
```

**Key schema facts:**
- `users.owner_id` is a self-referential FK — the owner user's `owner_id` equals their own `id`
- `employees` has a UNIQUE constraint on `(user_id, owner_id)` — one employee record per user per tenant
- `jobs.assigned_employee_id` references `employees.id` (NOT `users.id`)
- `jobs.status` CHECK constraint: `pending`, `scheduled`, `in_progress`, `completed`, `cancelled`
- `jobs.priority` CHECK constraint: `low`, `medium`, `high`, `urgent`
- User deletion is soft-delete (`is_active = FALSE`), not row removal
- Roles stored as strings with CHECK constraint: `owner`, `admin`, `manager`, `employee`, `viewer`

### JWT Token Structure

Every access token contains tenant context so services avoid database lookups:
```json
{
  "sub": "2",           // user_id (string)
  "email": "user@demo.com",
  "role": "employee",
  "owner_id": 1,        // tenant isolation key
  "company_id": 1,
  "jti": "unique-id",   // used for blacklisting
  "exp": 1738444800,     // 30-minute expiry
  "token_type": "access"
}
```

Refresh tokens are opaque strings (`secrets.token_urlsafe(48)`), stored as SHA-256 hashes in Postgres. They are NOT rotated on refresh — same token stays valid for 7 days.

### Role-Based Access Control

**Six roles exist** — defined in the DB CHECK constraint, Python enum (`UserRole`), JWT claims, and `ROLE_HIERARCHY`:

| Role | Hierarchy | Can View | Can Create/Edit | Can Delete | Can Invite | Can Manage Roles | Platform Admin |
|------|:---------:|:---:|:---:|:---:|:---:|:---:|:---:|
| `superadmin` | 100 | ✓ (all tenants) | ✓ | ✓ | ✓ | ✓ | ✓ |
| `owner` | 80 | ✓ | ✓ | ✓ | ✓ | ✓ | ✗ |
| `admin` | 60 | ✓ | ✓ | ✓ | ✓ | ✓ | ✗ |
| `manager` | 40 | ✓ | ✓ | Limited | ✗ | ✗ | ✗ |
| `employee` | 20 | ✓ | Own jobs only | ✗ | ✗ | ✗ | ✗ |
| `viewer` | 10 | ✓ | ✗ | ✗ | ✗ | ✗ | ✗ |

**Superadmin** is a platform-level role that sits above the tenant hierarchy. It has NO `owner_id`, NO `company_id`, and NO `organization_id` — it can impersonate any tenant and access all data across the platform. Superadmin users are managed through the `admin-bl-service`.

**Owner vs Admin:** Functionally identical for tenant-scoped operations. Every `require_role()` call uses `("owner", "admin")`. The structural difference is that an owner's `owner_id` is their own `id` (tenant root), whereas an admin's `owner_id` references the tenant owner.

**Role definitions are in:**
- **Python enum** — `services/user-db-access-service/app/models/user.py` (`UserRole`)
- **SQL constraint** — `scripts/init-db.sql` (`CONSTRAINT valid_role`)
- **Hierarchy** — `services/shared/common/auth.py` (`ROLE_HIERARCHY`)
- **BL/Auth schemas** — `services/user-bl-service/app/schemas.py` and `services/auth-service/app/schemas/auth.py`

Role enforcement uses a numeric hierarchy in `common/auth.py`:
```python
ROLE_HIERARCHY = {
    "superadmin": 100, "owner": 80, "admin": 60,
    "manager": 40, "employee": 20, "viewer": 10,
}
```

`require_role()` checks `>=` against the hierarchy. `require_superadmin` is an alias for `require_role("superadmin")`.

**Superadmin specifics:**
- `owner_id=NULL`, `organization_id=NULL`, `company_id=NULL` in JWT
- Can impersonate any non-superadmin user (creates 15-min shadow token)
- All admin actions are logged to the immutable `audit_logs` table
- Cannot impersonate other superadmins

---

## File Organization

### Backend Service Structure

```
services/<service-name>/
├── app/
│   ├── main.py                 # FastAPI app, lifespan, routers
│   ├── models/                 # SQLAlchemy ORM models
│   ├── schemas/                # Pydantic request/response schemas
│   ├── crud/                   # Database operations
│   ├── api/
│   │   └── routes.py           # FastAPI route handlers
│   ├── dependencies.py         # FastAPI dependency injection
│   ├── service_client.py       # HTTP client to other services (BL only)
│   └── tests/
│       ├── conftest.py         # Pytest fixtures
│       └── test_*.py           # Test modules
├── Dockerfile
└── requirements.txt
```

### Frontend Structure

```
services/frontend/
├── app/
│   ├── main.py
│   ├── routes/
│   │   ├── auth.py             # Login/logout page routes
│   │   ├── calendar.py         # Calendar page + HTMX partials
│   │   ├── customers.py        # Customer page + HTMX partials
│   │   ├── employees.py        # Employees page route
│   │   └── api_proxy.py        # Proxy /api/* to BL services
│   ├── templates/
│   │   ├── base.html           # Layout + authFetch()
│   │   ├── pages/              # Full pages
│   │   └── partials/           # HTMX fragments
│   ├── static/
│   │   ├── css/
│   │   └── js/
│   └── tests/
```

---

## API Endpoint Reference

### Auth Service (`:8005`)

| Route | Method | Purpose | Auth Required |
|-------|--------|---------|:---:|
| `/api/v1/auth/login` | POST | Exchange email/password for access+refresh tokens | ✗ |
| `/api/v1/auth/refresh` | POST | Get new access token from refresh token | ✗ |
| `/api/v1/auth/verify` | POST | S2S token validation (returns `valid: true/false`, never 401) | ✗ |
| `/api/v1/auth/logout` | POST | Revoke refresh token + blacklist access token | ✓ |
| `/api/v1/auth/revoke-all` | POST | Revoke all sessions for a user | ✓ (owner/admin) |
| `/api/v1/auth/me` | GET | Current user context from JWT | ✓ |
| `/api/v1/auth/impersonate` | POST | Create shadow token (impersonate a user) | ✓ (superadmin) |
| `/api/v1/auth/cleanup` | POST | Prune expired tokens | ✓ (admin) |

### User DB Access (`:8001`) — Internal Only

| Route | Method | Purpose |
|-------|--------|---------|
| `/api/v1/users` | GET | List users (filterable by `owner_id`, `is_active`, `role`) |
| `/api/v1/users` | POST | Create user (409 on duplicate email) |
| `/api/v1/users/{id}` | GET | Get user with employee details |
| `/api/v1/users/{id}` | PUT | Update user |
| `/api/v1/users/{id}` | DELETE | Soft-delete (set `is_active=False`) |
| `/api/v1/employees` | POST | Create employee details |
| `/api/v1/employees/{id}` | GET/PUT | Get or update employee |
| `/api/v1/users/{id}/employees` | GET | List employees under an owner |
| `/api/v1/companies` | POST | Create company |
| `/api/v1/companies/{id}` | GET/PUT | Get or update company |
| `/api/v1/internal/authenticate` | POST | S2S credential verification (always returns 200) |

### Job BL Service (`:8006`)

| Route | Method | Purpose | Auth Required |
|-------|--------|---------|:---:|
| `/api/v1/jobs` | GET | List jobs (tenant-scoped) | ✓ |
| `/api/v1/jobs` | POST | Create job (validates customer ownership) | ✓ |
| `/api/v1/jobs/calendar` | GET | Calendar view (date range, grouped by day) | ✓ |
| `/api/v1/jobs/queue` | GET | Unscheduled job queue | ✓ |
| `/api/v1/jobs/{id}` | GET | Get job with enriched names | ✓ |
| `/api/v1/jobs/{id}` | PUT | Update job | ✓ |
| `/api/v1/jobs/{id}` | DELETE | Delete job | ✓ (owner/admin) |
| `/api/v1/jobs/{id}/assign` | POST | Assign to employee (conflict detection) | ✓ (owner/admin) |
| `/api/v1/jobs/{id}/schedule` | POST | Schedule to time slot (conflict detection) | ✓ (owner/admin) |
| `/api/v1/jobs/{id}/status` | PUT | Update status only | ✓ |
| `/api/v1/jobs/{id}/check-conflicts` | POST | Preview scheduling conflicts | ✓ |

### Customer BL Service (`:8007`) and Customer DB Access (`:8002`)

Follow the same pattern as Job BL/DB — CRUD for customers and customer_notes, tenant-scoped.

### User BL Service (`:8004`)

Follow the same pattern — CRUD for users and employees, tenant-scoped, role-gated.

### Admin BL Service (`:8008`)

Platform administration — every endpoint requires `superadmin` role.

| Route | Method | Purpose | Auth Required |
|-------|--------|---------|:---:|
| `/api/v1/admin/organizations` | GET | List all organizations | ✓ (superadmin) |
| `/api/v1/admin/organizations` | POST | Create organization | ✓ (superadmin) |
| `/api/v1/admin/organizations/{id}` | GET | Get organization | ✓ (superadmin) |
| `/api/v1/admin/organizations/{id}` | PUT | Update organization | ✓ (superadmin) |
| `/api/v1/admin/organizations/{id}/suspend` | POST | Suspend organization | ✓ (superadmin) |
| `/api/v1/admin/organizations/{id}/unsuspend` | POST | Reactivate organization | ✓ (superadmin) |
| `/api/v1/admin/audit-logs` | GET | Query audit trail | ✓ (superadmin) |
| `/api/v1/admin/settings` | GET | List platform settings | ✓ (superadmin) |
| `/api/v1/admin/settings/{key}` | GET/PUT | Get or update setting | ✓ (superadmin) |
| `/api/v1/admin/users` | GET | Cross-tenant user list | ✓ (superadmin) |
| `/api/v1/admin/users/{id}` | GET | Cross-tenant user detail | ✓ (superadmin) |

### All Services

Every service exposes `GET /api/v1/health` → `{ status: "healthy", service: "...", version: "1.0.0" }`.

---

## Docker & Dockerfile Patterns

### Build Context

All Dockerfiles use `./services` as the build context (set in `docker-compose.yml`). This is why they can access the shared library:

```dockerfile
COPY shared /app/shared
COPY auth-service/app /app/app
```

### Standard Dockerfile Template

```dockerfile
FROM python:3.11-slim
ENV PYTHONPATH=/app:/app/shared
# Install system deps for asyncpg
RUN apt-get update && apt-get install -y gcc libpq-dev && rm -rf /var/lib/apt/lists/*
# Layer caching: requirements first
COPY <service>/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt
COPY shared /app/shared
COPY <service>/app /app/app
RUN useradd -m appuser && chown -R appuser:appuser /app
USER appuser
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "<port>"]
```

### Service Dependencies (docker-compose.yml)

```
nginx-gateway → frontend, auth, all BL services (healthy)
frontend → auth, all BL services (healthy)
BL services → their DB-access service + auth-service (healthy)
auth-service → db + user-db-access + redis (healthy)
DB-access services → db (healthy)
```

### Health Checks

All services have health checks defined in `docker-compose.yml` using Python's `urllib.request` to hit `/health`. Health checks run every 5s with a 10s start period.

---

## Common Pitfalls to Avoid

❌ **Don't create tests for features that don't exist**
✅ Verify the actual code before writing tests

❌ **Don't use plain `fetch()` for authenticated endpoints**
✅ Use `authFetch()` helper in frontend

❌ **Don't forget tenant isolation in queries**
✅ Always filter by `owner_id` from JWT context

❌ **Don't expose DB-access services externally**
✅ They're internal-only, blocked by NGINX at `/api/v1/internal/*`

❌ **Don't use blocking I/O in async functions**
✅ Use `await` for database, Redis, HTTP calls

❌ **Don't hardcode service URLs**
✅ Use `settings.<service>_url` from `common/config.py`

❌ **Don't create new test files when one already exists**
✅ Add to existing test modules (e.g., `test_employees.py`)

❌ **Don't decode JWTs in BL services**
✅ Call `auth-service /api/v1/auth/verify` via HTTP — BL services never see the JWT secret

❌ **Don't add database queries to BL services**
✅ BL services call DB-access services via HTTP — they never import SQLAlchemy models

❌ **Don't add auth/role checks to DB-access services**
✅ DB-access services are raw CRUD — all access control happens in BL services

❌ **Don't confuse `assigned_to` (API) with `assigned_employee_id` (DB)**
✅ Field translation happens in `service_client.py` — use the correct name for the layer you're editing

❌ **Don't reference `users.id` for job assignment**
✅ `jobs.assigned_employee_id` references `employees.id` — the employee table, not the users table

❌ **Don't assume Redis is available**
✅ All cache operations are wrapped in try/catch — the app must work without Redis

❌ **Don't add `/api/jobs/{path}` routes before specific routes like `/api/jobs/calendar`**
✅ Specific routes must be registered BEFORE catch-all `{path:path}` routes in the frontend proxy

❌ **Don't call `async_init_db()` in BL services**
✅ Only DB-access services and auth-service call this — BL services don't touch the database

❌ **Don't allow non-superadmin access to admin endpoints**
✅ All admin-bl-service routes use `require_superadmin` — no exceptions

❌ **Don't impersonate superadmin users**
✅ The impersonation endpoint explicitly blocks superadmin-to-superadmin impersonation

❌ **Don't skip audit logging on admin state changes**
✅ Use `common.audit.log_action()` for all create/update/delete/suspend operations in admin-bl-service

---

## Demo Credentials

For testing and development:

| Role | Email | Password |
|------|-------|----------|
| Superadmin | `superadmin@system.local` | `SuperAdmin123!` |
| Owner | `owner@demo.com` | `password123` |
| Admin | `admin@demo.com` | `password123` |
| Employee | `employee@demo.com` | `password123` |

---

## Quick Reference

### Service Ports

| Service | Port | Access |
|---------|------|--------|
| NGINX Gateway | 80 | **PUBLIC** |
| Frontend | 8000 | Internal |
| User DB Access | 8001 | Internal (blocked by NGINX) |
| Customer DB Access | 8002 | Internal (blocked by NGINX) |
| Job DB Access | 8003 | Internal (blocked by NGINX) |
| User BL | 8004 | Internal (via NGINX) |
| Auth | 8005 | Internal (via NGINX) |
| Job BL | 8006 | Internal (via NGINX) |
| Customer BL | 8007 | Internal (via NGINX) |
| Admin BL | 8008 | Internal (via NGINX, superadmin only) |
| PostgreSQL | 5432 | Exposed (dev only) |
| Redis | 6379 | Internal |

### Key Files

| Purpose | Location |
|---------|----------|
| Service URLs & config | `services/shared/common/config.py` |
| Custom exceptions | `services/shared/common/exceptions.py` |
| Shared Pydantic schemas | `services/shared/common/schemas.py` |
| Database engine & sessions | `services/shared/common/database.py` |
| Redis cache helpers | `services/shared/common/redis.py` |
| Shared auth dependencies | `services/shared/common/auth.py` |
| Audit trail helper | `services/shared/common/audit.py` |
| Database schema & seed data | `scripts/init-db.sql` |
| JWT helper (frontend) | `services/frontend/app/templates/base.html:306-329` |
| Frontend API proxy routing | `services/frontend/app/routes/api_proxy.py` |
| NGINX routing & security | `services/nginx/nginx.conf` |
| Auth token CRUD (JWT, refresh, blacklist) | `services/auth-service/app/crud/auth.py` |
| Auth endpoints | `services/auth-service/app/api/routes.py` |
| Job BL field translation & caching | `services/job-bl-service/app/service_client.py` |
| Job scheduling conflict logic | `services/job-bl-service/app/logic/scheduling.py` |
| BL auth dependency (token verify via HTTP) | `services/job-bl-service/app/dependencies.py` |
| Admin BL service routes | `services/admin-bl-service/app/api/routes.py` |
| Admin BL service client | `services/admin-bl-service/app/service_client.py` |
| Admin frontend portal | `services/frontend/app/routes/admin.py` |
| Admin portal template | `services/frontend/app/templates/pages/admin.html` |
| Docker orchestration | `docker-compose.yml` |
| Architecture docs | `docs/CLAUDE.md`, `README.md` |

---

## Commit Standards

When making changes:

1. **Test first** — Run tests before committing
2. **One concern per commit** — Don't mix unrelated changes
3. **Clear messages** — Describe *why*, not just *what*

```bash
# Good commit messages
git commit -m "fix(auth): use authFetch in employees page to include JWT token"
git commit -m "test(frontend): add comprehensive tests for employees page auth"

# Bad commit messages
git commit -m "fixed stuff"
git commit -m "updates"
```

---

**Last Updated:** February 13, 2026  
**Maintained By:** Development Team
