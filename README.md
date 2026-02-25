# CRM Calendar — Multi-Tenant Workflow Platform

A **multi-tenant workflow and calendar management platform** for small service businesses. Built as a layered microservices application with **12 Docker services**, **417 automated tests**, and enterprise-grade security including a **superadmin** role for platform-wide administration.

Business owners sign up, create their company workspace, invite employees, manage customers, and schedule jobs — all within an isolated tenant that is invisible to every other business on the platform.

---

## Table of Contents

- [What Does This App Do?](#what-does-this-app-do)
- [Architecture Overview](#architecture-overview)
- [How the Layers Work Together](#how-the-layers-work-together)
- [Authentication & Login Flow](#authentication--login-flow)
- [Multi-Tenancy — Data Isolation](#multi-tenancy--data-isolation)
- [Superadmin — Platform Administration](#superadmin--platform-administration)
- [Request Lifecycle — End to End](#request-lifecycle--end-to-end)
- [Database Schema](#database-schema)
- [Service Reference](#service-reference)
- [Redis Caching Strategy](#redis-caching-strategy)
- [Frontend & UI](#frontend--ui)
- [Getting Started](#getting-started)
- [Running Tests](#running-tests)
- [Integration Tests](#integration-tests)
- [CI/CD Pipeline](#cicd-pipeline)
- [SonarQube Code Quality](#sonarqube-code-quality)
- [Security Scanning (Trivy)](#security-scanning-trivy)
- [Project Structure](#project-structure)
- [Environment Variables](#environment-variables)
- [Technologies Used](#technologies-used)

---

## What Does This App Do?

CRM Calendar is a platform for trades and service businesses (plumbers, electricians, cleaning companies, etc.) to manage their day-to-day operations:

| Feature | What It Does |
|---------|-------------|
| **Calendar** | Visual month-view calendar showing all scheduled jobs. Click a day to see details, drag to reschedule. |
| **Job Management** | Create, assign, and track jobs through their lifecycle: pending → scheduled → in progress → completed. |
| **Employee Management** | Invite team members, assign roles, track skills and hourly rates. |
| **Customer Records** | Store customer contact details, addresses, and company information. |
| **Customer Notes** | Attach notes to customers — call logs, follow-ups, preferences. |
| **Scheduling** | Assign jobs to employees with automatic conflict detection (no double-booking). |
| **Job Queue** | Unscheduled jobs sit in a sidebar queue ready to be dragged onto the calendar. |
| **Multi-Business** | Multiple businesses share the platform but each one's data is completely invisible to others. |
| **Admin Portal** | Superadmin-only dashboard for managing organizations, viewing audit trails, platform settings, and user impersonation. |

---

## Architecture Overview

The application follows a **layered microservices** design. Each layer has a clear responsibility and communicates only with the layer directly below it.

```
                              ┌────────────────────────────┐
                              │       Client Browser       │
                              └─────────────┬──────────────┘
                                            │  Port 80
                              ┌─────────────▼──────────────┐
                              │     NGINX API Gateway      │
                              │   Rate limiting · Security  │
                              │   headers · Gzip · Routing  │
                              └──┬────┬────┬────┬────┬─────┘
          ┌───────────────────────┘    │    │    │    └───────────────────────┐
          ▼                           ▼    │    ▼                            ▼
  ┌───────────────┐  ┌────────────────┐   │  ┌─────────────────┐  ┌──────────────────┐
  │   Frontend    │  │  Auth Service  │   │  │  Job BL Service │  │ Customer BL Svc  │
  │    :8000      │  │     :8005      │   │  │     :8006       │  │      :8007       │
  │ (Jinja2+HTMX) │  │  (JWT, Login,  │   │  │  (Scheduling,   │  │   (CRUD, Notes,  │
  │               │  │  Multi-tenant) │   │  │   Conflicts,    │  │   Enrichment)    │
  └───────────────┘  └───────┬────────┘   │  │   Calendar)     │  └────────┬─────────┘
                             │            │  └───────┬─────────┘           │
                             │  ┌─────────▼──┐       │                     │
                             │  │ User BL Svc│       │                     │
                             │  │   :8004    │       │                     │
                             │  │(Users,Roles│       │                     │
                             │  │Invitations)│       │                     │
                             │  └──────┬─────┘       │                     │
       ┌───────────────────────────────┼─────────────┼─────────────────────┘
       │  DB Access Layer    │         │             │  (Internal only — blocked by NGINX)
       ▼                     ▼         ▼             ▼
  ┌───────────────┐  ┌────────────────┐  ┌─────────────────┐
  │ Customer DB   │  │   User DB      │  │    Job DB       │
  │ Access :8002  │  │  Access :8001  │  │   Access :8003  │
  └───────┬───────┘  └───────┬────────┘  └────────┬────────┘
          │                  │                     │
          └──────────────────┼─────────────────────┘
                             ▼
                   ┌──────────────────┐       ┌──────────────────┐
                   │   PostgreSQL     │       │      Redis       │
                   │     :5432        │       │      :6379       │
                   │   (9 tables)     │       │  (Caching + Auth)│
                   └──────────────────┘       └──────────────────┘
```

> **Note:** The Auth Service talks **directly** to User DB Access (`:8001`) — it calls `POST /internal/authenticate` to verify credentials and look up user details. It does not go through a BL layer.

### Layer Responsibilities

| Layer | Services | What It Does |
|-------|----------|-------------|
| **Gateway** | NGINX (:80) | The only public port. Handles rate limiting, security headers, compression, and routes requests to the correct service. Blocks direct access to DB services. |
| **Presentation** | Frontend (:8000) | Renders HTML pages using Jinja2 templates with HTMX for live partial updates and Alpine.js for interactive components. |
| **Authentication** | Auth Service (:8005) | Issues and verifies JWT tokens, manages refresh tokens, maintains a token blacklist in Redis for instant revocation. |
| **Business Logic** | User BL (:8004), Job BL (:8006), Customer BL (:8007), Admin BL (:8008) | Enforces permissions, tenant isolation, scheduling rules, and data enrichment. Validates every request through the Auth Service before touching data. The Admin BL service is restricted to the `superadmin` role and provides platform-wide administration. |
| **Data Access** | User DB (:8001), Customer DB (:8002), Job DB (:8003) | Pure database CRUD. No authentication, no business rules. Only reachable from inside the Docker network. |
| **Caching** | Redis (:6379) | Token blacklist (instant logout), response caching for BL services (reduces database load). |
| **Storage** | PostgreSQL (:5432) | 9 tables with automatic timestamps, audit trails, and demo seed data. |

> **Why separate BL and DB layers?** This separation means the data layer can be replicated or optimised without affecting business rules. The BL layer benefits from Redis caching to avoid redundant database calls. Each layer scales independently.

---

## How the Layers Work Together

When a user interacts with the app, their request passes through every layer. Here is what happens when an employee views a job:

```
  Employee clicks on a job in the calendar
    │
    ▼
  ┌─────────────────────────────────────────────────────────────────────┐
  │  1. BROWSER                                                        │
  │     authFetch('/api/v1/jobs/42') automatically attaches the        │
  │     JWT token from localStorage as a Bearer header                 │
  └──────────────────────────────┬──────────────────────────────────────┘
                                 │
                                 ▼
  ┌─────────────────────────────────────────────────────────────────────┐
  │  2. NGINX GATEWAY  (Port 80)                                       │
  │     • Checks rate limit (30 req/s per IP)                          │
  │     • Adds security headers (HSTS, X-Frame-Options, etc.)          │
  │     • Path /api/v1/jobs/* → forwards to job-bl-service:8006        │
  └──────────────────────────────┬──────────────────────────────────────┘
                                 │
                                 ▼
  ┌─────────────────────────────────────────────────────────────────────┐
  │  3. JOB BL SERVICE  (Port 8006)                                    │
  │     a) Extracts the Bearer token from the request                  │
  │     b) Sends token to auth-service:8005/api/v1/auth/verify         │
  │     c) Auth service decodes JWT → returns user_id, owner_id, role  │
  │     d) BL service checks: does the job belong to this tenant?      │
  │     e) Fetches the job from job-db-access-service:8003             │
  │     f) Fetches the customer name from customer-db-access:8002      │
  │     g) Fetches the employee name from user-db-access:8001          │
  │     h) Merges everything into one enriched response                │
  └──────────────────────────────┬──────────────────────────────────────┘
                                 │
                                 ▼
  ┌─────────────────────────────────────────────────────────────────────┐
  │  4. RESPONSE                                                       │
  │     {                                                              │
  │       "id": 42,                                                    │
  │       "title": "Kitchen Renovation",                               │
  │       "customer_name": "John Smith",     ← enriched                │
  │       "assigned_to_name": "Demo Employee", ← enriched              │
  │       "status": "scheduled",                                       │
  │       "start_time": "2026-02-13T09:00:00Z"                        │
  │     }                                                              │
  └─────────────────────────────────────────────────────────────────────┘
```

**Key point:** The BL service never trusts the caller. It always verifies the JWT through the Auth Service first, then uses the `owner_id` claim to ensure the user can only see data belonging to their business.

---

## Authentication & Login Flow

### How Login Works

Authentication uses **JWT (JSON Web Tokens)** — short-lived access tokens for API requests and longer-lived refresh tokens to stay logged in.

```
  ┌──────────┐          ┌─────────┐          ┌──────────┐          ┌──────────┐
  │  Browser │          │  NGINX  │          │   Auth   │          │ User DB  │
  │          │          │  :80    │          │  Service │          │ Access   │
  └────┬─────┘          └────┬────┘          └────┬─────┘          └────┬─────┘
       │  POST /api/v1/auth/login                 │                     │
       │  { email, password }                     │                     │
       │─────────────────────►│                    │                     │
       │                      │────────────────────►                    │
       │                      │                    │                     │
       │                      │     Step 1: Forward credentials         │
       │                      │                    │──────────────────────►
       │                      │                    │  POST /internal/    │
       │                      │                    │  authenticate       │
       │                      │                    │  {email, password}  │
       │                      │                    │                     │
       │                      │                    │  Step 2: User DB    │
       │                      │                    │  looks up email,    │
       │                      │                    │  verifies bcrypt    │
       │                      │                    │  hash, returns      │
       │                      │                    │  user_id, role,     │
       │                      │                    │  owner_id,          │
       │                      │                    │  company_id         │
       │                      │                    │◄──────────────────────
       │                      │                    │                     │
       │                      │     Step 3: Auth service creates:       │
       │                      │     • JWT access token (30 min)         │
       │                      │       with user_id, email, role,        │
       │                      │       owner_id, company_id baked in     │
       │                      │     • Random refresh token              │
       │                      │       (hashed + stored in DB)           │
       │                      │                    │                     │
       │                      │◄────────────────────                    │
       │◄─────────────────────│                    │                     │
       │                      │                    │                     │
       │  Step 4: Browser stores tokens in localStorage                 │
       │  Every future request uses authFetch() which                   │
       │  attaches "Authorization: Bearer <token>"                      │
       │                      │                    │                     │
```

### What's Inside a JWT Token

Every access token contains the full tenant context so services never need a database lookup to know who's asking:

```json
{
  "sub": "2",
  "email": "employee@demo.com",
  "role": "employee",
  "owner_id": 1,
  "company_id": 1,
  "jti": "a1b2c3d4e5f6",
  "exp": 1738444800,
  "token_type": "access"
}
```

| Claim | Purpose |
|-------|---------|
| `sub` | User's database ID |
| `email` | User's email address |
| `role` | Permission level (`owner`, `admin`, `employee`, `viewer`) |
| `owner_id` | **Tenant isolation key** — all data queries are filtered by this |
| `company_id` | Company metadata reference (name, address, branding) |
| `jti` | Unique token ID — used for blacklisting on logout |
| `exp` | Expiry timestamp — tokens are valid for 30 minutes |

### How BL Services Verify Every Request

No BL service trusts a token on its own. Every incoming request triggers a verification call to the Auth Service:

```python
# Inside every BL service (dependencies.py)
async def get_current_user(token: str) -> CurrentUser:
    # 1. Send the token to auth-service for validation
    resp = await auth_client.post(
        "http://auth-service:8005/api/v1/auth/verify",
        json={"access_token": token},
    )
    # 2. Auth service decodes the JWT, checks expiry,
    #    checks if the jti is blacklisted in Redis
    # 3. Returns user context or rejects with 401
    data = resp.json()
    return CurrentUser(
        user_id=data["user_id"],
        owner_id=data["owner_id"],  # ← The tenant key
        role=data["role"],
    )
```

### Token Refresh & Logout

| Action | What Happens |
|--------|-------------|
| **Token expires** | `authFetch()` in the browser detects a 401 response, silently calls `POST /api/v1/auth/refresh` with the refresh token, stores the new access token, and retries the original request. The user never notices. |
| **User logs out** | The refresh token is revoked in the database. The access token's `jti` is added to the Redis blacklist so it's rejected instantly on the next request. `localStorage` is cleared and the user is redirected to `/login`. |
| **Revoke all sessions** | All refresh tokens for the user are revoked at once. Useful if an account is compromised. |

### Rate Limiting

NGINX protects the auth endpoints from brute-force attacks:

| Endpoint | Rate Limit | Purpose |
|----------|-----------|---------|
| `/api/v1/auth/*` | 5 requests/second per IP | Prevents password guessing |
| `/api/v1/*` (all other API) | 30 requests/second per IP | General abuse prevention |

---

## Multi-Tenancy — Data Isolation

### The Simple Explanation

Think of the platform like an **apartment building**:

- Each **company** is a separate apartment (tenant)
- Each apartment has an **owner** (the business owner account)
- The owner can invite **employees** (team members with limited permissions)
- Each apartment has its own **customers, jobs, and notes**
- Nobody can see or access another apartment's data
- The building (database) is shared, but data is kept completely separate

### How It Works Technically

The system uses a **hybrid isolation model** combining two mechanisms:

| Mechanism | What It Does |
|-----------|-------------|
| `companies` table | Stores business identity — company name, address, phone, email, logo |
| `owner_id` on every resource | Provides fast, indexed data filtering without expensive JOINs |
| `company_id` on users | Links users to their company for metadata lookups |
| `company_id` in JWT | Embedded in every token so services have instant company context |

### The owner_id Chain

```
                    ┌─────────────────────────────────────────────┐
                    │              companies                      │
                    │  id=1  "Acme Plumbing Ltd."                 │
                    └───────────────────┬─────────────────────────┘
                                        │ company_id
                    ┌───────────────────▼─────────────────────────┐
                    │              users                          │
                    │  id=1  owner@acme.ie    role=owner          │
                    │  id=2  emp1@acme.ie     role=employee       │──── owner_id → 1
                    │  id=3  emp2@acme.ie     role=employee       │──── owner_id → 1
                    └──┬──────────────────────────────────────────┘
                       │ owner_id
        ┌──────────────┼──────────────┐
        ▼              ▼              ▼
  ┌──────────┐  ┌──────────┐  ┌──────────┐
  │customers │  │employees │  │  jobs    │
  │owner_id=1│  │owner_id=1│  │owner_id=1│
  └──────────┘  └──────────┘  └──────────┘
        │
        ▼
  ┌──────────────┐
  │customer_notes│
  └──────────────┘
```

Every query is automatically scoped by `owner_id`. A user from Acme Plumbing (`owner_id=1`) can never see data belonging to Widget Services (`owner_id=10`), because every SQL query includes `WHERE owner_id = <value from JWT>`.

### How `owner_id` Works — Step by Step

The `owner_id` column is the single most important field in the entire system. It is the mechanism that keeps every tenant's data completely separate in a shared database. Here is exactly how it works:

#### 1. Owner Registration

When a business owner signs up, a new row is inserted into the `users` table. The key detail is that **the owner's `owner_id` is set to their own `id`**:

```
INSERT INTO users (email, role, owner_id, company_id)
VALUES ('owner@acme.ie', 'owner', 1, 1);
--                                   ^
-- owner_id = their own user ID (self-referential)
```

This self-referential link is what makes the owner the root of their entire tenant hierarchy. Every piece of data created under this business will carry `owner_id = 1`.

#### 2. Employee Invitation

When the owner invites an employee, the new user's `owner_id` is set to **the owner's user ID** — not the employee's own ID:

```
INSERT INTO users (email, role, owner_id, company_id)
VALUES ('emp@acme.ie', 'employee', 1, 1);
--                                   ^
-- owner_id = the OWNER's ID, not the employee's
```

This means every user in a tenant shares the same `owner_id` value, which equals the owner's `users.id`.

#### 3. Data Creation

Whenever any user in the tenant creates a resource (customer, job, note, employee record), the system injects `owner_id` from their JWT token into the new record:

```python
# BL service — before sending data to DB-access service
payload["owner_id"] = current_user.owner_id  # From JWT, always 1 for this tenant
```

The user never sees or sets `owner_id` — it is injected automatically by the BL layer.

#### 4. Data Retrieval

Every list or get query passes `owner_id` as a filter to the DB-access layer:

```python
# BL service
response = await http_client.get(
    f"{db_service_url}/api/v1/customers",
    params={"owner_id": current_user.owner_id},  # Always from JWT
)

# DB-access service — resulting SQL
SELECT * FROM customers WHERE owner_id = 1;
```

Because the `owner_id` value comes from the **verified JWT** (which was signed by the auth service), a user can never tamper with it. They can only ever see data that belongs to their tenant.

#### 5. The Full Picture

Here is a concrete example with two separate businesses sharing the same database:

```
  Acme Plumbing (owner_id = 1)       Widget Services (owner_id = 10)
  ──────────────────────────          ────────────────────────────────
  users:                              users:
    id=1, owner@acme.ie, owner_id=1     id=10, boss@widget.ie, owner_id=10
    id=2, emp@acme.ie,   owner_id=1     id=11, staff@widget.ie, owner_id=10

  customers:                          customers:
    id=1, "John Smith",  owner_id=1     id=2, "Jane Doe",     owner_id=10

  jobs:                               jobs:
    id=1, "Fix sink",    owner_id=1     id=2, "Paint wall",   owner_id=10
```

When user `emp@acme.ie` (owner_id=1) requests `GET /api/v1/customers/`, the query returns **only** `John Smith`. `Jane Doe` is invisible because her `owner_id=10` does not match.

If user `emp@acme.ie` tries to access `GET /api/v1/customers/2` (Jane Doe), the BL service fetches the customer, sees `customer.owner_id (10) ≠ current_user.owner_id (1)`, and returns **403 Forbidden**.

#### 6. Superadmin Exception

Superadmin users have `owner_id = NULL` in their JWT. When a superadmin makes a request, the BL services detect the null owner_id and **skip tenant filtering**, allowing cross-tenant visibility for platform administration. This is why the DB-access layer accepts `owner_id` as an optional query parameter — when omitted, it returns data across all tenants.

### Isolation is Enforced at Every Layer

```
  1. User logs in
     └─ Auth service creates JWT with owner_id=1

  2. User requests GET /api/v1/customers/
     ├─ NGINX forwards to customer-bl-service
     ├─ BL service validates JWT → extracts owner_id=1
     ├─ BL service calls customer-db-access: GET /customers/?owner_id=1
     ├─ DB layer queries: SELECT * FROM customers WHERE owner_id = 1
     └─ Response contains ONLY this tenant's customers

  3. User tries to access another tenant's customer (GET /api/v1/customers/999)
     ├─ Customer 999 has owner_id=10 (different tenant)
     ├─ BL service checks: customer.owner_id ≠ current_user.owner_id
     └─ Returns 403 Forbidden

  4. Enforcement checkpoints:
     ✓ JWT extraction         (auth layer)
     ✓ owner_id filtering     (business logic layer)
     ✓ WHERE clause in SQL    (data access layer)
```

### Role-Based Access Control

Within a tenant, different roles have different permissions:

| Role | Can View Data | Can Create/Edit | Can Delete | Can Invite Users | Platform Admin |
|------|:---:|:---:|:---:|:---:|:---:|
| **Superadmin** | ✓ (all tenants) | ✓ | ✓ | ✓ | ✓ |
| **Owner** | ✓ | ✓ | ✓ | ✓ | ✗ |
| **Admin** | ✓ | ✓ | ✓ | ✓ | ✗ |
| **Manager** | ✓ | ✓ | Limited | ✗ | ✗ |
| **Employee** | ✓ | ✓ (own assigned jobs) | ✗ | ✗ | ✗ |
| **Viewer** | ✓ | ✗ | ✗ | ✗ | ✗ |

**Superadmin** is a platform-level role with cross-tenant visibility. Superadmins can manage organizations, view audit logs, adjust platform settings, and impersonate any non-superadmin user for troubleshooting. Impersonation produces a short-lived shadow token (15 min) with full audit trail.

Role enforcement happens in the BL layer using a `require_role()` dependency with a numeric hierarchy:

```python
# Only owners and admins can delete
@router.delete("/jobs/{job_id}")
async def delete_job(
    current_user = Depends(require_role("owner", "admin")),
):
    ...
```

---

## Superadmin — Platform Administration

The **superadmin** role provides platform-level management capabilities that sit *above* the normal tenant hierarchy. Superadmins manage organisations, monitor audit trails, configure system-wide settings, and — when necessary — impersonate tenant users for troubleshooting.

### What Can a Superadmin Do?

| Capability | Description |
|---|---|
| **Organisation Management** | Create, update, suspend, and reactivate organisations across the platform. |
| **Cross-Tenant User Visibility** | List and inspect users from *any* tenant, filtered by role, organisation, or active status. |
| **Audit Log Access** | Query the immutable audit trail with filters for actor, action, resource type, and organisation. |
| **Platform Settings** | View and update global key-value settings (e.g. maintenance mode, feature flags). |
| **User Impersonation** | Temporarily assume another user's identity to reproduce bugs or investigate support tickets. |

### Role Hierarchy

Every role is assigned a numeric level. Access checks use a **≥** comparison, so higher roles automatically inherit lower-role access:

```
superadmin : 100   ← platform-level, bypasses tenant scope
owner      :  80
admin      :  60
manager    :  40
employee   :  20
viewer     :  10
```

- `require_role("employee")` permits employee, manager, admin, owner, **and** superadmin.
- `require_superadmin()` performs a **direct role string check**, ignoring the hierarchy — only the literal `"superadmin"` role passes. This is used exclusively for admin-portal endpoints.

### How Superadmin Identity Differs

| JWT Claim | Normal User | Superadmin |
|---|---|---|
| `owner_id` | Tenant owner's user ID | `null` |
| `organization_id` | Org ID | `null` |
| `company_id` | Company ID | `null` |
| `role` | `owner` / `admin` / … | `superadmin` |

Because `owner_id` is `null`, superadmin requests **bypass tenant isolation** — they are not scoped to any single tenant's data.

### Impersonation (Shadow Tokens)

Impersonation allows a superadmin to act *as* another user without knowing their password. A **shadow token** is created with the target user's identity but retains a cryptographic audit trail to the superadmin.

**How it works:**

```
1. Superadmin calls  POST /api/v1/auth/impersonate
       body: { target_user_id: 42, reason: "Support ticket #1234" }

2. Auth service verifies:
   ✓ Caller is superadmin
   ✓ Target user exists
   ✓ Target user is NOT another superadmin

3. A shadow JWT is minted containing:
   - All of the target user's claims (sub, email, role, owner_id, …)
   - acting_as:       target user's owner_id
   - impersonator_id: superadmin's user ID
   - exp:             15-minute lifetime (deliberately short)

4. The shadow token is returned to the frontend, which:
   - Stores the original superadmin token
   - Replaces localStorage.access_token with the shadow token
   - Redirects to the calendar view as the impersonated user
```

**Shadow token JWT structure:**

```json
{
  "sub": "42",
  "email": "target@demo.com",
  "role": "employee",
  "owner_id": 5,
  "acting_as": 5,
  "impersonator_id": 1,
  "exp": 1738445700,
  "token_type": "access"
}
```

Every downstream BL service sees `impersonator_id` in the verified token and passes it to the audit logger. This means **every action taken during impersonation is fully traceable** back to the originating superadmin.

### Safety Measures & Security Controls

The superadmin feature includes multiple layers of defence:

#### 1. Superadmin-to-Superadmin Impersonation is Blocked

The `/auth/impersonate` endpoint explicitly rejects requests where the target user's role is `"superadmin"`. This prevents privilege escalation chains and ensures one superadmin cannot masquerade as another.

```python
if target.get("role") == "superadmin":
    raise HTTPException(403, "Cannot impersonate another superadmin")
```

#### 2. Shadow Tokens Expire in 15 Minutes

Normal access tokens last 30 minutes. Shadow (impersonation) tokens are deliberately limited to **15 minutes** to minimise the window of impersonated access. There is no refresh mechanism for shadow tokens — the superadmin must re-initiate impersonation if more time is needed.

#### 3. Immutable Audit Trail

Every state-changing admin operation is recorded in the `audit_logs` table, which is **append-only** — no update or delete operations are exposed. Each entry captures:

- **Who** — actor ID, email, and role
- **What** — action identifier (e.g. `auth.impersonate`, `org.suspend`)
- **Target** — resource type and ID
- **Context** — IP address, impersonator ID, free-form details JSON
- **When** — server-side timestamp

Impersonation events specifically record the target user, their role, and the reason provided by the superadmin.

#### 4. NGINX Blocks Direct Internal Access

The NGINX gateway blocks all requests to `/api/v1/internal/*` paths, ensuring DB-access services are never reachable from outside the Docker network. Admin BL service endpoints are only accessible via the authenticated proxy chain.

#### 5. Explicit Role Check (Not Hierarchy)

Admin-portal endpoints use `require_superadmin()`, which performs a **direct string comparison** (`role == "superadmin"`) rather than the hierarchy-based `>=` check. Even if a new role with a high numeric level were added, it would not gain admin access.

#### 6. Double-Submit Protection

The admin portal frontend disables mutation buttons during in-flight requests using a `submitting` guard, preventing accidental duplicate operations (e.g. creating the same organisation twice).

#### 7. Mandatory Impersonation Reason

The UI requires a non-empty reason string before submitting an impersonation request. This reason is recorded in the audit trail for accountability.

#### 8. Client-Side Access Gating

The admin portal page performs a server-side role verification on load via `GET /api/auth/me`. Non-superadmin users see an "Access Denied" message. This is **defence in depth** — the real enforcement happens at the API layer (admin-bl-service), not the frontend.

### Admin BL Service Architecture

The admin BL service follows the same layered pattern as all other BL services:

```
Browser → NGINX → Frontend Proxy → Admin BL Service → User DB-Access Service
                    /api/admin/*       :8008                  :8001
```

- **No direct DB access** — all data operations delegate to `user-db-access-service` via HTTP.
- **No JWT decoding** — token validation is delegated to `auth-service` via HTTP.
- **Every endpoint** is gated with `require_superadmin`.
- **Audit logging** uses the shared `common.audit.log_action()` fire-and-forget helper.

### Demo Credentials

| Role | Email | Password |
|---|---|---|
| Superadmin | `superadmin@system.local` | `SuperAdmin123!` |

---

## Request Lifecycle — End to End-TEST

This section traces a complete **create job** request from button click to database insert, showing exactly which services are involved and what each one does.

```
  ┌──────────────────────────────────────────────────────────────────┐
  │  STEP 1 — BROWSER                                               │
  │                                                                  │
  │  User fills in the "New Job" form and clicks Save.               │
  │  authFetch() sends POST /api/v1/jobs with the JWT token.         │
  └──────────────────────────────┬───────────────────────────────────┘
                                 ▼
  ┌──────────────────────────────────────────────────────────────────┐
  │  STEP 2 — NGINX  (Port 80)                                      │
  │                                                                  │
  │  • Applies rate limit (30 req/s)                                 │
  │  • Matches /api/v1/jobs/* → proxies to job-bl-service:8006      │
  │  • Adds security headers to the response                        │
  └──────────────────────────────┬───────────────────────────────────┘
                                 ▼
  ┌──────────────────────────────────────────────────────────────────┐
  │  STEP 3 — JOB BL SERVICE: AUTH CHECK  (Port 8006)               │
  │                                                                  │
  │  a) Extract Bearer token from Authorization header               │
  │  b) POST token to auth-service:8005/verify                      │
  │     → Auth service checks: is the token valid? Is it expired?    │
  │       Is the jti blacklisted in Redis?                           │
  │     → Returns: user_id=2, owner_id=1, role=employee              │
  └──────────────────────────────┬───────────────────────────────────┘
                                 ▼
  ┌──────────────────────────────────────────────────────────────────┐
  │  STEP 4 — JOB BL SERVICE: VALIDATE CUSTOMER  (Port 8006)        │
  │                                                                  │
  │  Before creating a job, the BL service must verify the           │
  │  customer actually belongs to the same tenant. The job-db        │
  │  service knows nothing about customers, so this cross-domain     │
  │  check can only happen at the BL layer.                          │
  │                                                                  │
  │  a) GET customer-db-access:8002/customers/{id}                  │
  │     → Fetches customer record including its owner_id             │
  │  b) Compare: customer.owner_id == current_user.owner_id?         │
  │     → If different tenant → 400 "Customer not found"             │
  │     → If same tenant → proceed                                   │
  └──────────────────────────────┬───────────────────────────────────┘
                                 ▼
  ┌──────────────────────────────────────────────────────────────────┐
  │  STEP 5 — JOB BL SERVICE: PREPARE PAYLOAD  (Port 8006)          │
  │                                                                  │
  │  a) Validate time: start_time must be before end_time            │
  │                                                                  │
  │  b) Translate field names (BL → DB):                             │
  │       assigned_to → assigned_employee_id                         │
  │       address → location                                         │
  │                                                                  │
  │  c) Inject tenant context from JWT:                              │
  │       payload["owner_id"] = current_user.owner_id                │
  │       payload["created_by_id"] = current_user.user_id            │
  └──────────────────────────────┬───────────────────────────────────┘
                                 ▼
  ┌──────────────────────────────────────────────────────────────────┐
  │  STEP 6 — JOB DB ACCESS SERVICE  (Port 8003)                    │
  │                                                                  │
  │  • Validates the payload against the Pydantic schema             │
  │  • Creates a SQLAlchemy Job object                               │
  │  • INSERT INTO jobs (...) VALUES (...)                           │
  │  • Returns the created job with its new ID and DB field names    │
  └──────────────────────────────┬───────────────────────────────────┘
                                 ▼
  ┌──────────────────────────────────────────────────────────────────┐
  │  STEP 7 — JOB BL SERVICE: POST-PROCESSING  (Port 8006)          │
  │                                                                  │
  │  a) Translate DB field names back to public API names:           │
  │       assigned_employee_id → assigned_to                         │
  │       location → address                                         │
  │                                                                  │
  │  b) Invalidate Redis cache keys:                                 │
  │       job:bl:jobs:*       (list caches)                          │
  │       job:bl:calendar:*   (calendar views)                       │
  │       job:bl:queue:*      (job queue)                            │
  │     Ensures next GET request fetches fresh data.                 │
  │                                                                  │
  │  c) Return 201 Created with the job in the public API format.    │
  └─────────────────────────────────────────────────────────────────┘
```

### Field Translation (BL ↔ DB)

The BL layer presents a user-friendly API with readable field names, while the DB layer uses precise database column names. Translation happens automatically in the service client:

| Public API (BL) | Database Column (DB) | Service |
|-----------------|---------------------|---------|
| `assigned_to` | `assigned_employee_id` | Job BL |
| `address` | `location` | Job BL |
| `first_name` + `last_name` | `name` | Customer BL |
| `company` | `company_name` | Customer BL |

---

## Database Schema

PostgreSQL 15 with **12 tables**, automatic `updated_at` triggers, and demo seed data.
All tables are created by [`scripts/init-db.sql`](scripts/init-db.sql) on first launch.

### Entity Relationship Diagram

```
  ┌────────────────┐
  │ organizations  │
  │────────────────│
  │ PK id          │◄──────────────────────────────────────────┐
  │ name           │                                           │
  │ slug (unique)  │                                           │
  │ billing_email  │                               organization_id
  │ billing_plan   │                                           │
  │ max_users      │                                           │
  │ max_customers  │                                           │
  │ is_active      │          ┌──────────────┐                 │
  │ suspended_at   │          │  companies   │                 │
  └────────────────┘          │──────────────│                 │
                              │ PK id        │◄──────────┐    │
                              │ FK org_id    │───────────►│    │
                              │ name         │            │    │
                              │ address      │            │    │
                              │ phone        │   company_id    │
                              │ email        │            │    │
                              │ eircode      │            │    │
                              └──────────────┘            │    │
                                                          │    │
                                ┌─────────────────────────┼────┼─────────────┐
                                │  ┌──────────────────┐   │    │             │
                                │  │      users       │   │    │             │
                                │  │──────────────────│   │    │             │
                                │  │ PK id            │◄──┼────┼───────┐     │
                                │  │ email (unique)   │   │    │       │     │
                                │  │ hashed_password  │   │    │ owner_id    │
                                │  │ first_name       │   │    │ (self-ref)  │
                                │  │ last_name        │   │    │       │     │
                                │  │ role             │───┼────┼───────┘     │
                                │  │ FK owner_id      │   │    │             │
                                │  │ FK company_id    │───┘    │             │
                                │  │ FK org_id        │────────┘             │
                                │  └──┬──────┬──────┬─┘                      │
                                │     │      │      │                        │
              ┌─────────────────┘     │      │      └──────────────────┐     │
              │                       │      │                         │     │
              ▼                       ▼      ▼                         ▼     │
  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐ │
  │  employees   │  │  customers   │  │    jobs      │  │ refresh_tokens   │ │
  │──────────────│  │──────────────│  │──────────────│  │──────────────────│ │
  │ PK id        │  │ PK id        │  │ PK id        │  │ PK id            │ │
  │ FK user_id   │  │ FK owner_id  │  │ FK owner_id  │  │ FK user_id       │ │
  │ FK owner_id  │  │ name         │  │ FK customer  │  │ token_hash       │ │
  │ department   │  │ email        │  │ FK employee  │  │ expires_at       │ │
  │ position     │  │ phone        │  │ FK created_by│  │ is_revoked       │ │
  │ hourly_rate  │  │ address      │  │ title        │  └──────────────────┘ │
  │ skills       │  │ company_name │  │ status       │                       │
  └──────────────┘  └──────┬───────┘  │ priority     │  ┌──────────────────┐ │
                           │          │ start_time   │  │ token_blacklist  │ │
                           ▼          │ end_time     │  │──────────────────│ │
                   ┌──────────────┐   │ location     │  │ PK id            │ │
                   │customer_notes│   └──────┬───────┘  │ jti (unique)     │ │
                   │──────────────│          │          │ FK user_id       │ │
                   │ PK id        │          ▼          │ expires_at       │ │
                   │ FK customer  │  ┌──────────────┐   └──────────────────┘ │
                   │ FK created_by│  │ job_history  │                        │
                   │ content      │  │──────────────│  ┌──────────────────┐  │
                   └──────────────┘  │ PK id        │  │   audit_logs     │  │
                                     │ FK job_id    │  │──────────────────│  │
                                     │ FK changed_by│  │ PK id            │  │
                                     │ field_changed│  │ FK actor_id      │──┘
                                     │ old_value    │  │ FK impersonator  │
                                     │ new_value    │  │ FK org_id        │
                                     └──────────────┘  │ action           │
                                                       │ details (JSONB)  │
                                                       └──────────────────┘
```

### Table Details

#### `organizations` — Platform-Level Entities

Top-level entity managed by superadmins. Each tenant (company + owner) belongs to exactly one organization. Superadmins can create, suspend, and manage organizations. Controls billing plans and resource limits.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | `SERIAL` | **PK** | Auto-incrementing ID |
| `name` | `VARCHAR(255)` | `NOT NULL` | Display name (e.g. "Acme Plumbing Co") |
| `slug` | `VARCHAR(100)` | `UNIQUE NOT NULL` | URL-friendly identifier (e.g. `acme-plumbing`) |
| `billing_email` | `VARCHAR(255)` | — | Email for billing/invoicing |
| `billing_plan` | `VARCHAR(50)` | `CHECK IN (free, starter, professional, enterprise)`, `DEFAULT 'free'` | Current subscription tier |
| `max_users` | `INTEGER` | `DEFAULT 50` | Maximum users allowed under this org |
| `max_customers` | `INTEGER` | `DEFAULT 500` | Maximum customer records allowed |
| `is_active` | `BOOLEAN` | `DEFAULT TRUE` | Active status — set `FALSE` when suspended |
| `suspended_at` | `TIMESTAMPTZ` | — | When the org was suspended (if applicable) |
| `suspended_reason` | `TEXT` | — | Why the org was suspended |
| `created_at` | `TIMESTAMPTZ` | auto | Record creation time |
| `updated_at` | `TIMESTAMPTZ` | auto-trigger | Last modification |

**Indexes:** `slug` (unique), `is_active`.

---

#### `companies` — Business Tenants

Each company represents one business using the platform. Links to all users via `company_id`.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | `SERIAL` | **PK** | Auto-incrementing ID |
| `organization_id` | `INTEGER` | `FK → organizations(id)` | Parent organization |
| `name` | `VARCHAR(255)` | `NOT NULL` | Company display name |
| `address` | `TEXT` | — | Business address |
| `phone` | `VARCHAR(50)` | — | Contact phone |
| `email` | `VARCHAR(255)` | — | Contact email |
| `eircode` | `VARCHAR(10)` | — | Irish postal code |
| `logo_url` | `VARCHAR(500)` | — | URL to company logo |
| `is_active` | `BOOLEAN` | `DEFAULT TRUE` | Soft-delete flag |
| `created_at` | `TIMESTAMPTZ` | auto | Record creation time |
| `updated_at` | `TIMESTAMPTZ` | auto-trigger | Last modification |

---

#### `users` — Accounts & Authentication

Login credentials and identity. The `owner_id` self-reference creates the tenant hierarchy — owners have `NULL`, employees point to their owner.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | `SERIAL` | **PK** | Auto-incrementing ID |
| `email` | `VARCHAR(255)` | `UNIQUE NOT NULL` | Login email |
| `hashed_password` | `VARCHAR(255)` | `NOT NULL` | Bcrypt hash |
| `first_name` | `VARCHAR(255)` | `NOT NULL` | First name |
| `last_name` | `VARCHAR(255)` | `NOT NULL` | Last name |
| `phone` | `VARCHAR(50)` | — | Contact phone |
| `role` | `VARCHAR(50)` | `CHECK IN (owner, admin, manager, employee, viewer)` | Permission level |
| `is_active` | `BOOLEAN` | `DEFAULT TRUE` | Soft-delete flag |
| `owner_id` | `INTEGER` | `FK → users(id)` | Tenant link — self-referential for owners |
| `company_id` | `INTEGER` | `FK → companies(id)` | Company metadata link |
| `organization_id` | `INTEGER` | `FK → organizations(id)` | Parent organization |
| `created_at` | `TIMESTAMPTZ` | auto | Record creation time |
| `updated_at` | `TIMESTAMPTZ` | auto-trigger | Last modification |

---

#### `employees` — Staff Profiles

Extended details for users who work under a business owner. Linked 1:1 with a `users` row.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | `SERIAL` | **PK** | Auto-incrementing ID |
| `user_id` | `INTEGER` | `NOT NULL FK → users(id)` | The user account |
| `owner_id` | `INTEGER` | `NOT NULL FK → users(id)` | The business owner |
| `department` | `VARCHAR(100)` | — | Department (e.g. "Operations") |
| `position` | `VARCHAR(100)` | — | Job title (e.g. "Technician") |
| `phone` | `VARCHAR(50)` | — | Contact phone |
| `hire_date` | `DATE` | — | Date hired |
| `hourly_rate` | `DECIMAL(10,2)` | — | Hourly pay rate |
| `skills` | `TEXT` | — | Comma-separated skills |
| `notes` | `TEXT` | — | Internal notes |
| `is_active` | `BOOLEAN` | `DEFAULT TRUE` | Active status |
| `created_at` | `TIMESTAMPTZ` | auto | Record creation time |
| `updated_at` | `TIMESTAMPTZ` | auto-trigger | Last modification |

**Unique constraint:** `(user_id, owner_id)` — one employee record per user per tenant.

---

#### `customers` — Client Records

Customer contact details belonging to a specific business via `owner_id`.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | `SERIAL` | **PK** | Auto-incrementing ID |
| `owner_id` | `INTEGER` | `NOT NULL FK → users(id)` | Tenant isolation |
| `name` | `VARCHAR(255)` | `NOT NULL` | Customer full name |
| `email` | `VARCHAR(255)` | — | Contact email |
| `phone` | `VARCHAR(50)` | — | Contact phone |
| `address` | `TEXT` | — | Street address |
| `eircode` | `VARCHAR(10)` | — | Irish postal code |
| `company_name` | `VARCHAR(255)` | — | Company name |
| `is_active` | `BOOLEAN` | `DEFAULT TRUE` | Soft-delete flag |
| `created_at` | `TIMESTAMPTZ` | auto | Record creation time |
| `updated_at` | `TIMESTAMPTZ` | auto-trigger | Last modification |

---

#### `customer_notes` — CRM Notes

Free-text notes attached to customers for tracking interactions, follow-ups, and preferences.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | `SERIAL` | **PK** | Auto-incrementing ID |
| `customer_id` | `INTEGER` | `NOT NULL FK → customers(id)` | The customer |
| `created_by_id` | `INTEGER` | `NOT NULL FK → users(id)` | Who wrote it |
| `content` | `TEXT` | `NOT NULL` | Note body |
| `created_at` | `TIMESTAMPTZ` | auto | When created |
| `updated_at` | `TIMESTAMPTZ` | auto-trigger | Last modification |

---

#### `jobs` — Work Orders & Calendar Events

The core scheduling entity. Jobs without a `start_time` appear in the unscheduled queue.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | `SERIAL` | **PK** | Auto-incrementing ID |
| `title` | `VARCHAR(255)` | `NOT NULL` | Short job title |
| `description` | `TEXT` | — | Detailed description |
| `customer_id` | `INTEGER` | `FK → customers(id)` | Customer (nullable for internal tasks) |
| `owner_id` | `INTEGER` | `NOT NULL FK → users(id)` | Tenant isolation |
| `assigned_employee_id` | `INTEGER` | `FK → employees(id)` | Assigned employee |
| `created_by_id` | `INTEGER` | `NOT NULL FK → users(id)` | Who created it |
| `status` | `VARCHAR(50)` | `CHECK IN (pending, scheduled, in_progress, completed, cancelled, on_hold)` | Lifecycle state |
| `priority` | `VARCHAR(50)` | `CHECK IN (low, normal, high, urgent)` | Priority level |
| `start_time` | `TIMESTAMPTZ` | — | Scheduled start |
| `end_time` | `TIMESTAMPTZ` | — | Scheduled end |
| `all_day` | `BOOLEAN` | `DEFAULT FALSE` | All-day event flag |
| `location` | `TEXT` | — | Job site address |
| `eircode` | `VARCHAR(10)` | — | Job site postal code |
| `estimated_duration` | `INTEGER` | — | Estimated minutes |
| `actual_duration` | `INTEGER` | — | Actual minutes |
| `notes` | `TEXT` | — | Internal notes |
| `color` | `VARCHAR(20)` | — | Calendar display colour |
| `is_recurring` | `BOOLEAN` | `DEFAULT FALSE` | Recurring event flag |
| `recurrence_rule` | `VARCHAR(500)` | — | iCal-style recurrence rule |
| `parent_job_id` | `INTEGER` | `FK → jobs(id)` | Parent job (for recurring instances) |
| `created_at` | `TIMESTAMPTZ` | auto | Record creation time |
| `updated_at` | `TIMESTAMPTZ` | auto-trigger | Last modification |

**Indexes:** `owner_id`, `customer_id`, `assigned_employee_id`, `status`, `start_time`, composite `(start_time, end_time)` for calendar range queries.

---

#### `job_history` — Audit Trail

Every change to a job is recorded here for accountability. Who changed what, when, and what the old value was.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | `SERIAL` | **PK** | Auto-incrementing ID |
| `job_id` | `INTEGER` | `NOT NULL FK → jobs(id)` | The job that changed |
| `changed_by_id` | `INTEGER` | `NOT NULL FK → users(id)` | Who made the change |
| `change_type` | `VARCHAR(50)` | — | Type of change (e.g. update, status_change) |
| `field_changed` | `VARCHAR(100)` | — | Which field was modified |
| `old_value` | `TEXT` | — | Previous value |
| `new_value` | `TEXT` | — | New value |
| `created_at` | `TIMESTAMPTZ` | auto | When the change occurred |

---

#### `refresh_tokens` — Session Management

Stores hashed refresh tokens. The raw token is never saved — only a SHA-256 hash is kept.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | `SERIAL` | **PK** | Auto-incrementing ID |
| `user_id` | `INTEGER` | `NOT NULL FK → users(id)` | Token owner |
| `owner_id` | `INTEGER` | `NOT NULL` | Tenant context |
| `token_hash` | `VARCHAR(64)` | `UNIQUE NOT NULL` | SHA-256 hash of the refresh token |
| `device_info` | `VARCHAR(255)` | — | Browser/device identifier |
| `ip_address` | `VARCHAR(45)` | — | IP at time of issue |
| `expires_at` | `TIMESTAMPTZ` | `NOT NULL` | Token expiry (7 days) |
| `is_revoked` | `BOOLEAN` | `DEFAULT FALSE` | Set `TRUE` on logout |
| `created_at` | `TIMESTAMPTZ` | auto | When issued |

---

#### `token_blacklist` — Revoked Access Tokens

When a user logs out, their access token's `jti` is stored here (and in Redis) so it's rejected immediately — even before its natural 30-minute expiry.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | `SERIAL` | **PK** | Auto-incrementing ID |
| `jti` | `VARCHAR(36)` | `UNIQUE NOT NULL` | The JWT ID of the revoked token |
| `user_id` | `INTEGER` | `NOT NULL FK → users(id)` | Whose token |
| `expires_at` | `TIMESTAMPTZ` | `NOT NULL` | Can be pruned after this time |
| `created_at` | `TIMESTAMPTZ` | auto | When blacklisted |

---

#### `audit_logs` — Platform Audit Trail

Records all significant platform actions. Every superadmin action, impersonation, login, and sensitive operation writes a row here for compliance and traceability. Rows are immutable — no UPDATE/DELETE.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | `BIGSERIAL` | **PK** | Auto-incrementing ID (big integer for high volume) |
| `timestamp` | `TIMESTAMPTZ` | `DEFAULT CURRENT_TIMESTAMP` | When the action occurred |
| `actor_id` | `INTEGER` | `FK → users(id)` | Who performed the action |
| `actor_email` | `VARCHAR(255)` | — | Denormalised email for fast display |
| `actor_role` | `VARCHAR(50)` | — | Role at time of action |
| `impersonator_id` | `INTEGER` | `FK → users(id)` | If acting under impersonation, the real superadmin |
| `organization_id` | `INTEGER` | `FK → organizations(id)` | Which org the action affected |
| `action` | `VARCHAR(100)` | `NOT NULL` | Action identifier (e.g. `user.create`, `org.suspend`) |
| `resource_type` | `VARCHAR(100)` | — | Type of resource (e.g. `organization`, `user`) |
| `resource_id` | `VARCHAR(100)` | — | ID of the affected resource |
| `details` | `JSONB` | `DEFAULT '{}'` | Arbitrary structured metadata (reason, old/new values, etc.) |
| `ip_address` | `VARCHAR(45)` | — | IP of the actor (supports IPv6) |

**Indexes:** `timestamp`, `actor_id`, `organization_id`, `action`, composite `(resource_type, resource_id)`.

---

#### `platform_settings` — System Configuration

Key-value store for system-wide configuration. Superadmins can read/write these via the admin API.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `key` | `VARCHAR(100)` | **PK** | Setting identifier (e.g. `maintenance_mode`) |
| `value` | `JSONB` | `NOT NULL DEFAULT '{}'` | Setting value (JSON for flexibility) |
| `description` | `TEXT` | — | Human-readable description |
| `updated_by` | `INTEGER` | `FK → users(id)` | Last superadmin who changed it |
| `updated_at` | `TIMESTAMPTZ` | auto-trigger | When last modified |

### Database Triggers & Functions

| Object | Purpose |
|--------|---------|
| `update_updated_at_column()` | Trigger function that sets `updated_at = CURRENT_TIMESTAMP` on every `UPDATE` |
| Triggers on 7 tables | `organizations`, `companies`, `users`, `employees`, `customers`, `customer_notes`, `jobs` — all auto-update `updated_at` |
| Trigger on `platform_settings` | Auto-updates `updated_at` when a superadmin changes a setting |
| `cleanup_expired_auth_tokens()` | Maintenance function that prunes expired rows from `refresh_tokens` and `token_blacklist` |

### Seed Data

The database is pre-loaded with demo data by [`scripts/init-db.sql`](scripts/init-db.sql) on first launch. This provides a fully functional environment for immediate testing without needing to create any data manually.

#### Organizations

| Field | Value |
|-------|-------|
| **Name** | Default Organization |
| **Slug** | `default-org` |
| **Billing email** | `billing@demoservices.ie` |
| **Billing plan** | `professional` |
| **Max users** | 50 |
| **Max customers** | 500 |
| **Active** | Yes |

The organization is the top-level grouping. All companies and users in the demo belong to this single organization. Superadmins manage organizations — they can create new ones, suspend them, change billing plans, or adjust user/customer limits.

**What is stored about each organization:**
- **Identity:** Name and URL-friendly slug (used in routing and lookups)
- **Billing:** Contact email, subscription plan (free / starter / professional / enterprise)
- **Resource limits:** Maximum number of users and customers the org is allowed to create
- **Status:** Active flag, suspension timestamp and reason (for compliance/audit)
- **Timestamps:** Created and last-updated dates (auto-managed by triggers)

#### Company

| Field | Value |
|-------|-------|
| **Name** | Demo Services Ltd. |
| **Address** | 456 Business Park, Dublin |
| **Phone** | +353 1 555 0100 |
| **Email** | info@demoservices.ie |
| **Eircode** | D04 AB12 |
| **Organization** | Default Organization |
| **Active** | Yes |

The company represents the actual business (tenant). It belongs to one organization and all users within the tenant share the same `company_id`.

#### Users

| # | Email | Name | Role | Password | owner_id | company_id | Notes |
|---|-------|------|------|----------|----------|-----------|-------|
| 1 | `owner@demo.com` | Demo Owner | `owner` | `password123` | 1 (self) | 2 | Tenant owner — `owner_id` points to own `id` |
| 2 | `employee@demo.com` | Demo Employee | `employee` | `password123` | 1 | 2 | Regular employee under the owner |
| 5 | `superadmin@system.local` | System Administrator | `superadmin` | `SuperAdmin123!` | `NULL` | `NULL` | Platform admin — no tenant affiliation |

The superadmin has `NULL` for `owner_id`, `company_id`, and `organization_id` because they operate above the tenant level and can manage all organizations.

#### Employees (Staff Profiles)

| # | User | Position | Department | Hourly Rate | Skills | Hire Date |
|---|------|----------|------------|-------------|--------|-----------|
| 1 | Demo Employee | Field Technician | Operations | €35.50 | Electrical, Plumbing, Carpentry | ~6 months ago |

Employee records extend a user with HR-specific data: department, position, hourly rate, skills, notes, and hire date. The `(user_id, owner_id)` unique constraint ensures one employee profile per user per tenant.

#### Customers

| # | Name | Email | Phone | Address | Eircode | Company |
|---|------|-------|-------|---------|---------| --------|
| 1 | John Smith | john.smith@example.com | +353 1 987 6543 | 123 Main Street, Dublin | D02 XY45 | Smith & Co. |

All customers are scoped to `owner_id = 1` (the demo owner). Customer data includes name, contact details, address, Irish postal code (Eircode), and an optional company name.

#### Jobs

| # | Title | Status | Priority | Customer | Scheduled | Duration |
|---|-------|--------|----------|----------|-----------|----------|
| 1 | Kitchen Renovation Consultation | `scheduled` | `normal` | John Smith | 2 days ahead | 120 min |
| 2 | Follow-up Call | `pending` | `high` | — | Unscheduled | 30 min |

Job #1 has a `start_time` + `end_time` so it appears on the calendar. Job #2 has no time slot, so it sits in the **Job Queue** sidebar until scheduled.

#### Platform Settings

| Key | Value | Description |
|-----|-------|-------------|
| `maintenance_mode` | `false` | When `true`, only superadmins can access the platform |
| `max_login_attempts` | `5` | Maximum failed login attempts before account lockout |
| `default_billing_plan` | `"free"` | Default billing plan assigned to new organizations |
| `platform_version` | `"1.1.0"` | Current platform version string (reference only) |

Platform settings are stored as JSONB values and managed by superadmins through the admin API. They control system-wide behaviour like maintenance windows, security thresholds, and default configuration for new tenants.

#### How Seed Data Relates

```
Organization: Default Organization (slug: default-org)
  └── Company: Demo Services Ltd. (id: 2)
        ├── Owner: owner@demo.com (user 1, owner_id = 1)
        │     ├── Employee: employee@demo.com (user 2)
        │     │     └── Employee Profile: Field Technician, €35.50/hr
        │     ├── Customer: John Smith (Smith & Co.)
        │     │     └── Job: Kitchen Renovation Consultation (scheduled)
        │     └── Job: Follow-up Call (pending, in queue)
        └── Superadmin: superadmin@system.local (user 5)
              └── No tenant affiliation (owner_id = NULL)
```

---

## Service Reference

### NGINX API Gateway (Port 80)

The **only publicly exposed port**. All other services communicate internally on the Docker network.

| Feature | Detail |
|---------|--------|
| Rate limiting | 5 req/s on auth endpoints, 30 req/s general API |
| Security headers | X-Frame-Options, X-Content-Type-Options, HSTS, Referrer-Policy, Permissions-Policy |
| Compression | Gzip level 6 on text, JSON, JS, CSS, SVG |
| Internal blocking | `/api/v1/internal/*` returns 403 — DB services are never reachable externally |
| Static caching | `/static/*` cached 7 days with `immutable` directive |
| Logging | JSON-structured access logs |

**Routing Table:**

| Path | Upstream Service | Rate Limit |
|------|-----------------|------------|
| `/api/v1/auth/*` | auth-service:8005 | 5 req/s |
| `/api/v1/users/*`, `/api/v1/employees/*`, `/api/v1/company` | user-bl-service:8004 | 30 req/s |
| `/api/v1/jobs/*` | job-bl-service:8006 | 30 req/s |
| `/api/v1/customers/*`, `/api/v1/notes/*` | customer-bl-service:8007 | 30 req/s |
| `/api/v1/admin/*` | admin-bl-service:8008 | 10 req/s |
| `/static/*` | frontend:8000 | cached |
| `/*` (catch-all) | frontend:8000 | 30 req/s |

---

### Auth Service (Port 8005)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/auth/login` | POST | Exchange email + password for access token + refresh token |
| `/api/v1/auth/refresh` | POST | Get a new access token using a refresh token |
| `/api/v1/auth/verify` | POST | Service-to-service: validate a JWT (called by every BL service) |
| `/api/v1/auth/logout` | POST | Revoke one session (blacklist access token, revoke refresh token) |
| `/api/v1/auth/revoke-all` | POST | Revoke all sessions for a user |
| `/api/v1/auth/me` | GET | Return current user context from token |
| `/api/v1/auth/impersonate` | POST | Create a shadow token for user impersonation (superadmin only) |
| `/api/v1/health` | GET | Health check |

---

### User BL Service (Port 8004)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/users/` | GET | List users (tenant-scoped) |
| `/api/v1/users/` | POST | Create user (owner/admin only) |
| `/api/v1/users/{id}` | GET | Get user by ID |
| `/api/v1/users/{id}` | PUT | Update user |
| `/api/v1/users/{id}` | DELETE | Deactivate user (owner/admin only) |
| `/api/v1/users/invite` | POST | Invite employee (creates user + employee in one step) |
| `/api/v1/employees/` | GET | List employees in tenant |
| `/api/v1/employees/` | POST | Create employee details |
| `/api/v1/employees/{id}` | GET | Get employee by ID |
| `/api/v1/employees/{id}` | PUT | Update employee |
| `/api/v1/company` | GET | Get current user's company details |
| `/api/v1/company` | PUT | Update company (owner/admin only) |

---

### Job BL Service (Port 8006)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/jobs/` | GET | List jobs (filterable by status, employee, customer) |
| `/api/v1/jobs/` | POST | Create job (validates customer belongs to tenant) |
| `/api/v1/jobs/calendar` | GET | Calendar view — jobs grouped by day in a date range |
| `/api/v1/jobs/queue` | GET | Unscheduled job queue |
| `/api/v1/jobs/{id}` | GET | Get job enriched with customer and employee names |
| `/api/v1/jobs/{id}` | PUT | Update job |
| `/api/v1/jobs/{id}` | DELETE | Delete job (owner/admin only) |
| `/api/v1/jobs/{id}/assign` | POST | Assign job to employee (with conflict check) |
| `/api/v1/jobs/{id}/schedule` | POST | Schedule job to time slot (with conflict check) |
| `/api/v1/jobs/{id}/status` | PUT | Update job status |
| `/api/v1/jobs/{id}/check-conflicts` | POST | Preview scheduling conflicts without committing |

---

### Customer BL Service (Port 8007)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/customers/` | GET | List/search customers (tenant-scoped) |
| `/api/v1/customers/search` | GET | Dedicated search (autocomplete) |
| `/api/v1/customers/` | POST | Create customer |
| `/api/v1/customers/{id}` | GET | Get customer (enriched with jobs + notes) |
| `/api/v1/customers/{id}` | PUT | Update customer |
| `/api/v1/customers/{id}` | DELETE | Soft-delete (owner/admin only) |
| `/api/v1/notes/{customer_id}` | GET | List customer notes |
| `/api/v1/notes/{customer_id}` | POST | Add customer note |
| `/api/v1/notes/{id}` | PUT | Update a note |
| `/api/v1/notes/{id}` | DELETE | Delete a note (owner/admin only) |

---

### Admin BL Service (Port 8008)

Platform administration — **superadmin role only**. Every endpoint verifies the caller has the `superadmin` role before processing. All state-changing operations are logged to the audit trail.

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/admin/organizations` | GET | List all organizations on the platform |
| `/api/v1/admin/organizations` | POST | Create a new organization |
| `/api/v1/admin/organizations/{id}` | GET | Get organization details |
| `/api/v1/admin/organizations/{id}` | PUT | Update organization |
| `/api/v1/admin/organizations/{id}/suspend` | POST | Suspend organization (with reason) |
| `/api/v1/admin/organizations/{id}/unsuspend` | POST | Reactivate a suspended organization |
| `/api/v1/admin/audit-logs` | GET | Query audit trail (filterable by action, actor) |
| `/api/v1/admin/settings` | GET | List all platform settings |
| `/api/v1/admin/settings/{key}` | GET | Get a specific setting value |
| `/api/v1/admin/settings/{key}` | PUT | Update a platform setting |
| `/api/v1/admin/users` | GET | List users across all tenants |
| `/api/v1/admin/users/{id}` | GET | Get user details (cross-tenant) |

---

### DB Access Services (Internal Only)

These three services handle all direct database operations. They have **no authentication** and are **blocked by NGINX** from external access. Only BL services can reach them via the Docker network.

| Service | Port | Manages | Key Operations |
|---------|------|---------|---------------|
| **User DB Access** | 8001 | `users`, `employees`, `companies` | User CRUD, employee profiles, password verification, company metadata |
| **Customer DB Access** | 8002 | `customers`, `customer_notes` | Customer CRUD, search by name/email/phone, notes management |
| **Job DB Access** | 8003 | `jobs`, `job_history` | Job CRUD, calendar views, queue (unscheduled), status tracking, audit history |

---

## Redis Caching Strategy

Redis 7 provides sub-millisecond caching across the platform. Each service uses a separate logical database to avoid key collisions.

| Redis DB | Service | What's Cached | Key Prefixes |
|----------|---------|--------------|-------------|
| DB 0 | Auth Service | Blacklisted token JTIs (instant logout) | `bl:<jti>` |
| DB 1 | User BL | User and employee query results | `user:bl:user:*`, `user:bl:users:*`, `user:bl:employees:*` |
| DB 2 | Job BL | Jobs, calendar views, job queue | `job:bl:job:*`, `job:bl:jobs:*`, `job:bl:calendar:*`, `job:bl:queue:*` |
| DB 3 | Customer BL | Customers and notes | `cust:bl:customer:*`, `cust:bl:customers:*`, `cust:bl:notes:*` |
| DB 4 | Admin BL | Organization and settings cache | `admin:bl:org:*`, `admin:bl:settings:*` |

### Cache Behaviour

| Operation | What Happens |
|-----------|-------------|
| **Read (GET)** | Check Redis first → on miss, fetch from DB service, store in Redis with TTL |
| **Write (POST/PUT/DELETE)** | Delete the specific cache key + pattern-wipe related list caches |
| **TTL (short)** | 30 seconds — paginated lists, calendar views |
| **TTL (medium)** | 120 seconds — single-resource lookups |
| **TTL (long)** | 300 seconds — rarely-changing reference data |
| **Redis failure** | Graceful degradation — errors are logged but never block the request |

### Configuration

| Setting | Value |
|---------|-------|
| Max memory | 128 MB |
| Eviction policy | `allkeys-lru` (least recently used) |
| Persistence | AOF (append-only file) on Docker volume |
| Health check | `redis-cli ping` every 3 seconds |

---

## Frontend & UI

### Technology Stack

| Technology | Purpose |
|-----------|---------|
| **Jinja2** | Server-side HTML rendering with template inheritance (`base.html` → `pages/` → `partials/`) |
| **HTMX 1.9.10** | HTML-driven AJAX — partial page updates without writing JavaScript (e.g. calendar month navigation) |
| **Alpine.js 3.x** | Lightweight reactivity for modals, dropdowns, and form state |
| **Tailwind CSS (CDN)** | Utility-first CSS framework — no build step required |

### Client-Side Authentication

Authentication is handled entirely in the browser — no server-side sessions:

1. User submits credentials on `/login` → `POST /api/v1/auth/login`
2. Tokens are stored in `localStorage` (access token, refresh token, user role, owner ID)
3. Every `fetch()` call uses the `authFetch()` wrapper which injects `Authorization: Bearer <token>` automatically
4. HTMX requests also receive the Bearer header via an `htmx:configRequest` event listener
5. On 401, `authFetch()` silently refreshes the token and retries the request
6. Logout clears `localStorage` and redirects to `/login`

### Pages

| Route | Description |
|-------|-------------|
| `/login` | Sign-in page (standalone, no navbar) |
| `/calendar` | Main page — month-view calendar with job cards |
| `/employees` | Employee list with details |
| `/customers` | Customer list with search, detail panels, and modals |
| `/admin` | Admin portal — organizations, audit logs, settings, user impersonation (superadmin only) |

### HTMX Partials

| Route | What It Renders |
|-------|----------------|
| `/calendar/grid` | Calendar grid (month navigation) |
| `/calendar/day/{date}` | Day detail panel |
| `/calendar/job-queue` | Unscheduled job sidebar |
| `/calendar/job-modal` | Job create/edit modal |
| `/customers/create-modal` | New customer modal |
| `/customers/edit-modal/{id}` | Edit customer modal |
| `/customers/detail/{id}` | Customer detail side-panel |
| `/customers/delete-confirm/{id}` | Delete confirmation dialog |

---

## Getting Started

### Prerequisites

- [Docker](https://docs.docker.com/get-docker/) and Docker Compose
- Python 3.11+ (only for local development)

### Quick Start

```bash
# 1. Clone and navigate
git clone <repository-url>
cd yr4-projectdevelopmentrepo

# 2. Copy environment template
cp .env.example .env

# 3. Build and start all services
docker-compose up -d --build

# 4. Open the application
#    → http://localhost
```

### Demo Credentials

| Role | Email | Password |
|------|-------|----------|
| Superadmin | `superadmin@system.local` | `SuperAdmin123!` |
| Owner | `owner@demo.com` | `password123` |
| Employee | `employee@demo.com` | `password123` |

### Useful Commands

```bash
# View logs for a specific service
docker-compose logs -f auth-service

# Restart a single service after code changes
docker-compose up -d --build job-bl-service

# Stop everything
docker-compose down

# Stop and remove all data volumes
docker-compose down -v
```

### Local Development

For running a service outside Docker with hot-reload:

```bash
# 1. Start only the database and Redis
docker-compose up -d db redis

# 2. Create a virtual environment
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # macOS/Linux

# 3. Install dependencies
pip install -r services/auth-service/requirements.txt

# 4. Run with hot-reload
cd services/auth-service
uvicorn app.main:app --port 8005 --reload
```

---

## Running Tests

The platform includes **417 automated tests** across 9 services. Tests are per-service following microservices best practices.

```bash
# Run all unit tests via Docker (per-service)
docker-compose exec -T auth-service pytest app/tests/ -v
docker-compose exec -T user-db-access-service pytest tests/ -v
docker-compose exec -T customer-db-access-service pytest tests/ -v
docker-compose exec -T job-db-access-service pytest tests/ -v
docker-compose exec -T user-bl-service pytest app/tests/ -v
docker-compose exec -T job-bl-service pytest app/tests/ -v
docker-compose exec -T customer-bl-service pytest app/tests/ -v
docker-compose exec -T frontend pytest app/tests/ -v

# Run all unit tests with the helper scripts
./scripts/test-all.sh              # Linux/macOS
.\scripts\run-all-tests.ps1        # Windows PowerShell
```

### Unit Test Breakdown

| Service | Tests | What's Tested |
|---------|:-----:|---------------|
| Auth Service | 69 | Login, JWT creation, token refresh, blacklisting, session revocation, impersonation, cleanup endpoint, security |
| User DB Access | 73 | User CRUD, employee profiles, company CRUD, organizations, audit logs, platform settings, internal auth, 404 paths |
| Job DB Access | 44 | Job CRUD, calendar views, queue ordering, status history, include_history param, multi-tenant isolation, 404 paths |
| Customer DB Access | 41 | Customer CRUD, search, notes CRUD, soft-delete, reactivation, include_notes param, pagination |
| Job BL | 30 | Tenant isolation, scheduling conflicts, calendar endpoint, assign endpoint, data enrichment, role enforcement |
| Frontend | 95 | Page rendering, HTMX partials, auth pages (login/logout), admin portal, API proxy, calendar navigation |
| User BL | 17 | Tenant scoping, role-based access, employee invitations, company management |
| Customer BL | 17 | Tenant isolation, field translation, notes enrichment, note update/delete endpoints, cross-tenant protection |
| Admin BL | 31 | Organization CRUD, user endpoints, security access control, platform settings, audit logging |
| **Total** | **417** | |

### Unit Testing Methodology

| Layer | Approach | Why |
|-------|----------|-----|
| **DB Access** | In-memory SQLite database | Fast (no Docker needed), tests real CRUD logic with a SQLite stand-in for Postgres |
| **Business Logic** | Mock downstream services | Tests rules and permissions in isolation without network calls |
| **Frontend** | Test client rendering | Verifies pages, partials, and UI elements render correctly using FastAPI's TestClient |

---

## Integration Tests

> **Added in iteration-testing branch — February 2026**

Integration tests validate **real service-to-service communication** with no mocks. They spin up the full Docker Compose stack (all 11 services, PostgreSQL, Redis) and run HTTP requests against live endpoints through NGINX.

### Why Both Pairwise and E2E Tests?

The integration test suite uses **two complementary strategies**:

| Strategy | What It Tests | Why It Matters |
|----------|-------------|----------------|
| **Pairwise tests** | Individual service pairs (e.g., job-bl ↔ job-db-access) | Isolates failures to a specific domain. If `test_job_flow` fails, you know the issue is in the job services — not auth or customers. Faster to debug. |
| **E2E smoke tests** | The critical business path through ALL layers | Catches cross-cutting issues that pairwise tests miss: NGINX routing misconfigurations, auth token propagation failures, field name translation bugs between BL and DB layers. |

> **The rationale:** Unit tests catch logic bugs in isolation. Pairwise integration tests catch communication bugs between specific service pairs. E2E tests catch system-level bugs that only appear when all 11 services talk to each other simultaneously. No single test type is sufficient alone — each layer catches problems the others miss.

### Integration Test Files

```
tests/integration/
├── conftest.py              # Shared fixtures: HTTP client, auth tokens, health check
├── test_auth_flow.py        # Pairwise: auth-service ↔ user-db-access
├── test_user_flow.py        # Pairwise: user-bl ↔ user-db-access
├── test_customer_flow.py    # Pairwise: customer-bl ↔ customer-db-access
├── test_job_flow.py         # Pairwise: job-bl ↔ job-db-access
├── test_e2e_smoke.py        # Full E2E: NGINX → BL → DB-access → Postgres
└── requirements.txt         # httpx, pytest, pytest-ordering
```

### What's Covered

| Test File | Tests | What's Validated |
|-----------|:-----:|-----------------|
| `test_auth_flow.py` | 10 | Login (valid/invalid), token verify, /auth/me, refresh, logout + blacklist |
| `test_user_flow.py` | 5 | List users (tenant-scoped), get user by ID, list employees, auth required |
| `test_customer_flow.py` | 6 | Customer CRUD (create, update, delete), customer notes, auth required |
| `test_job_flow.py` | 8 | Job CRUD, calendar endpoint, queue endpoint, status update, auth required |
| `test_e2e_smoke.py` | 8 | Health checks, NGINX routing to all services, internal routes blocked, full business workflow (create customer → create job → update status → verify calendar) |

### Running Integration Tests Locally

```bash
# 1. Start the full stack
docker compose up -d --build

# 2. Wait for all services to be healthy
docker compose ps  # All should show "healthy"

# 3. Run integration tests (from inside the network)
docker compose -f docker-compose.yml -f ci/docker-compose.ci.yml run --rm integration-runner

# Or run directly from your machine (if you have Python + httpx installed):
INTEGRATION_BASE_URL=http://localhost pytest tests/integration/ -v
```

### How Integration Tests Work in CI

In the GitLab CI pipeline, integration tests run as **Stage 6** (on `main` branch only):

1. Docker-in-Docker builds the full stack from source
2. `docker compose up -d` starts all 11 services + Postgres + Redis
3. The pipeline waits for all health checks to pass (up to 120s)
4. An `integration-runner` container joins the Docker network
5. The runner executes `pytest tests/integration/ -v` against `http://nginx-gateway`
6. Service logs are captured as artifacts for debugging failures
7. All containers are torn down after tests complete

---

## Project Structure

```
yr4-projectdevelopmentrepo/
├── .gitlab-ci.yml                  # 7-stage CI/CD pipeline definition
├── .gitignore                      # Git ignore rules
├── docker-compose.yml              # Orchestrates all 11 application services
├── .env.example                    # Environment variable template
├── README.md                       # This file
│
├── ci/                             # CI/CD configuration files
│   ├── .trivy.yaml                 # Trivy scanner configuration
│   ├── docker-compose.ci.yml       # CI override (no host ports, deterministic env)
│   ├── docker-compose.sonarqube.yml # SonarQube server (dev tooling, separate stack)
│   └── sonar-project.properties    # SonarQube scanner settings
│
├── docs/                           # Project documentation
│   ├── AGENTS.md                   # AI coding agent guidelines
│   ├── CI_README.md                # CI/CD setup & usage guide
│   └── CLAUDE.md                   # Claude-specific context
│
├── assets/                         # Project images and logos
│   ├── Logo no background.png
│   ├── logo no text.png
│   └── logo.png
│
├── scripts/
│   ├── init-db.sql                 # DB schema, triggers, seed data
│   ├── test-all.sh                 # Run all unit tests (Linux/macOS)
│   └── run-all-tests.ps1           # Run all unit tests (Windows)
│
├── tests/
│   └── integration/                # Integration test suite (full-stack, no mocks)
│       ├── conftest.py             # HTTP client, auth tokens, health check
│       ├── test_auth_flow.py       # Pairwise: auth ↔ user-db-access
│       ├── test_user_flow.py       # Pairwise: user-bl ↔ user-db-access
│       ├── test_customer_flow.py   # Pairwise: customer-bl ↔ customer-db-access
│       ├── test_job_flow.py        # Pairwise: job-bl ↔ job-db-access
│       ├── test_e2e_smoke.py       # Full E2E through NGINX
│       └── requirements.txt        # httpx, pytest, pytest-ordering
│
└── services/
    ├── .dockerignore               # Excludes tests/caches from Docker builds
    ├── shared/common/              # Shared library (imported by all services)
    │   ├── config.py               # Pydantic Settings — URLs, secrets, TTLs
    │   ├── database.py             # Async SQLAlchemy engine + session factory
    │   ├── redis.py                # Async Redis client + cache helpers
    │   ├── schemas.py              # Common response schemas
    │   └── exceptions.py           # Base exception hierarchy
    │
    ├── nginx/                      # API Gateway — routes, rate limits, security
    ├── auth-service/               # JWT auth — login, refresh, verify, blacklist
    ├── user-bl-service/            # Users + employees — permissions, invitations
    ├── job-bl-service/             # Jobs — scheduling, conflicts, calendar
    ├── customer-bl-service/        # Customers — CRUD, notes, enrichment
    ├── user-db-access-service/     # User/employee database operations
    ├── customer-db-access-service/ # Customer/notes database operations
    ├── job-db-access-service/      # Job/history database operations
    └── frontend/                   # Jinja2 + HTMX + Alpine.js web UI
```

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `POSTGRES_USER` | `crm_user` | PostgreSQL username |
| `POSTGRES_PASSWORD` | `crm_password` | PostgreSQL password |
| `POSTGRES_DB` | `crm_calendar` | Database name |
| `SECRET_KEY` | `your-secret-key-...` | JWT signing key (**change in production**) |
| `DEBUG` | `false` | Debug mode |
| `DATABASE_URL` | auto | PostgreSQL connection string |
| `REDIS_URL` | `redis://redis:6379/<db>` | Redis connection (DB 0-3 per service) |
| `USER_SERVICE_URL` | `http://user-db-access-service:8001` | User DB service |
| `CUSTOMER_SERVICE_URL` | `http://customer-db-access-service:8002` | Customer DB service |
| `JOB_SERVICE_URL` | `http://job-db-access-service:8003` | Job DB service |
| `AUTH_SERVICE_URL` | `http://auth-service:8005` | Auth service |
| `USER_BL_SERVICE_URL` | `http://user-bl-service:8004` | User BL service |
| `JOB_BL_SERVICE_URL` | `http://job-bl-service:8006` | Job BL service |
| `CUSTOMER_BL_SERVICE_URL` | `http://customer-bl-service:8007` | Customer BL service |
| `CACHE_TTL_SHORT` | `30` | Cache TTL for lists (seconds) |
| `CACHE_TTL_MEDIUM` | `120` | Cache TTL for single resources |
| `CACHE_TTL_LONG` | `300` | Cache TTL for reference data |

---

## CI/CD Pipeline

> **Status:** Implemented in the `iteration-testing` branch — February 2026. The pipeline is defined in `.gitlab-ci.yml` and runs on GitLab CI/CD.

### Pipeline Architecture

The pipeline has **7 stages**. Feature branches run Stages 1–2 for fast feedback (~3-5 min). Merges to `main` run all 7 stages including Aikido security scans, Docker builds, integration tests, image scanning, and deployment (~15-20 min).

```
Feature branches / MRs (~3-5 min):

┌─────────────────────────────────┐    ┌───────────┐
│ Stage 1: Unit Tests (8 parallel)│───▶│ Stage 2:  │
│ + Trivy Code Scan (parallel)    │    │ SonarQube │
└─────────────────────────────────┘    └───────────┘

main branch — full pipeline (~15-20 min):

┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────┐  ┌──────────┐
│ 1. Unit  │─▶│ 2. Sonar │─▶│ 3. Aikido│─▶│ 4. Build │─▶│ 5. Integ │─▶│ 6. Trivy Img │─▶│ 7.Deploy │
│  Tests   │  │   Qube   │  │  Source  │  │  Images  │  │  Tests   │  │ + Aikido Rel │  │ (manual) │
│ + Trivy  │  │          │  │   Scan   │  │          │  │ (pre-    │  │  (parallel)  │  │          │
│CodeScan  │  │          │  │          │  │          │  │  built)  │  │              │  │          │
└──────────┘  └──────────┘  └──────────┘  └──────────┘  └──────────┘  └──────────────┘  └──────────┘
```

### Stage Details

| Stage | Tool | What Happens | Runs On | Blocks On |
|:-----:|------|-------------|---------|-----------|
| **1a. Unit Tests** | pytest + pytest-xdist | 8 parallel test jobs (one per service). DB-access services spin up Postgres service containers. Produces Cobertura coverage XML reports. | All branches + MRs | Any test failure or <80% coverage |
| **1b. Dependency Scan** | Trivy (`trivy fs`) | Scans all `requirements.txt` files and Python source for known CVEs. Runs in parallel with unit tests (`needs: []`). | All branches + MRs | CRITICAL severity CVEs |
| **2. Code Quality** | SonarQube | `sonar-scanner` sends code + coverage reports to self-hosted SonarQube. Analyses bugs, code smells, duplication, and coverage on new code. Waits for quality gate. | All branches + MRs | Quality gate failure |
| **3. Source Security** | Aikido Security | **Fail-fast gate** — SAST, SCA, secrets detection, IaC misconfiguration. Catches security issues BEFORE building Docker images, saving ~10 min of CI time if it fails. | `main` only | Any security finding |
| **4. Build & Push** | Docker-in-Docker | Builds all 10 service Docker images. Tags with commit SHA + `:latest`. Pushes to container registry. Images reused by Stages 5, 6a, and 7. | `main` only | Build failure |
| **5. Integration Tests** | Docker Compose + pytest | Spins up full stack using pre-built images from Stage 4. Waits for health checks. Runs pairwise + E2E tests through NGINX. Service logs captured as artifacts. | `main` only | Any test failure |
| **6a. Image Scan** | Trivy (`trivy image`) | Scans each of the 10 built Docker images for OS-level vulnerabilities (openssl, libc, base image CVEs). Runs in parallel with 6b. | `main` only | CRITICAL severity CVEs |
| **6b. Release Gate** | Aikido Security | **Different from Stage 3.** Registers this commit as a release for **continuous monitoring** — Aikido alerts if new CVEs are published post-deploy. Can also scan container images. Final security gate. | `main` only | Any security finding |
| **7. Deploy** | `curl` → GitLab API | Triggers deployment repo (`yr4-projectdeploymentrepo`) pipeline, passing image tags. **Manual gate** — requires human ▶️ approval. | `main` only (manual) | Human approval |

### Design Decisions

| Decision | Rationale |
|----------|-----------|
| **`rules:` instead of `only:`** | Migrated from deprecated `only:` syntax to `rules:` for better control and forward compatibility with GitLab CI. |
| **`needs: []` on unit test jobs** | Makes parallelism explicit — all 8 test jobs + Trivy code scan start simultaneously without waiting for each other. |
| **SonarQube on all branches** | Code quality feedback should be available on every MR, not just `main`. Fast (~1-2 min) and gives developers immediate feedback in the MR diff. |
| **Trivy code scan on all branches** | Catches vulnerable dependencies early — before images are built. Free, fast (~1 min), offline-capable. |
| **Aikido source scan (Stage 3) as fail-fast** | Runs BEFORE the build stage. If a security issue is found, Stages 4–7 are skipped — saving ~10 min of CI time. Runs on `main` only to conserve API quota. |
| **Aikido release gate (Stage 6b) for monitoring** | Different purpose from Stage 3. Registers the release for **continuous monitoring** — Aikido alerts if a new CVE is published post-deploy. Can also scan container images via registry integration. |
| **Defence in depth (Trivy + Aikido)** | Trivy is free, fast, offline with its own CVE database. Aikido adds SAST, secrets detection, IaC scanning, and continuous monitoring. Different tools, different databases, broader coverage. |
| **Build once, reuse everywhere** | Docker images built in Stage 4 are reused by Stage 5 (integration tests), Stage 6a (Trivy image scan), and Stage 7 (deployment). No double-build waste. |
| **Image builds on `main` only** | Saves CI minutes. Feature branch code is validated by unit tests + Trivy + SonarQube; images are only built for code that has passed review and been merged. |
| **Manual deploy gate** | Automatic deployment to production is risky for a microservices app with 11 services. A human reviews the pipeline results before triggering deployment. |
| **Integration runner as a container** | Running tests inside the Docker network avoids port mapping issues. The runner hits `http://nginx-gateway` directly — same as services communicate internally. |
| **CRITICAL-only blocking for Trivy** | Blocking on CRITICAL only avoids false-positive fatigue. HIGH vulnerabilities are reported in artifacts for review but don't break the pipeline. |
| **Separate compose files** | `docker-compose.yml` (app), `ci/docker-compose.ci.yml` (CI overrides), `ci/docker-compose.sonarqube.yml` (dev tooling). Keeps each concern isolated and composable. |

### CI/CD Variables Required

These must be configured in GitLab (Settings → CI/CD → Variables):

| Variable | Purpose | Protected | Masked |
|----------|---------|:---------:|:------:|
| `SONAR_HOST_URL` | URL of SonarQube instance | No | No |
| `SONAR_TOKEN` | SonarQube authentication token | No | Yes |
| `AIKIDO_CLIENT_API_KEY` | Aikido Security CI API token ([generate at aikido.dev](https://app.aikido.dev)) | No (all branches) | Yes |
| `DEPLOY_REPO_TRIGGER_TOKEN` | Token to trigger deployment repo pipeline | Yes (main only) | Yes |
| `DEPLOY_REPO_TRIGGER_URL` | API URL for deployment repo trigger | Yes (main only) | No |
| `CI_REGISTRY` / `CI_REGISTRY_USER` / `CI_REGISTRY_PASSWORD` | Container registry credentials (auto-provided by GitLab CR) | — | Yes |

### Two-Repository Strategy

| Repository | What It Does |
|------------|-------------|
| **Dev Repo** (this repo) | All development happens here. CI pipeline runs tests, scans, builds images. |
| **Deployment Repo** ([yr4-projectdeploymentrepo](https://gitlab.comp.dkit.ie/finalproject/Prototypes/yr4-projectdeploymentrepo.git)) | Receives triggers from the dev repo pipeline. Handles staging deploy, E2E browser tests, and production deploy. |

Code flows: Dev Repo (`main` pipeline passes) → manual approval → trigger deployment repo → staging → production.

---

## SonarQube Code Quality

> **Added in iteration-testing branch — February 2026**

SonarQube Community Edition runs self-hosted via Docker. It analyses all Python services for bugs, code smells, duplication, and test coverage.

### Why SonarQube?

| What It Catches | Example |
|----------------|---------|
| **Bugs** | Unreachable code, null dereference, incorrect logic |
| **Code smells** | Functions too long, too many parameters, duplicated blocks |
| **Security hotspots** | Hardcoded credentials, SQL injection patterns, weak crypto |
| **Coverage gaps** | New code with <80% test coverage |
| **Duplication** | Copy-pasted code blocks across services |

### Setup Instructions

```bash
# 1. Start SonarQube server (separate from the app stack)
docker compose -f ci/docker-compose.sonarqube.yml up -d

# 2. Wait ~60 seconds for SonarQube to initialise
#    Open http://localhost:9000 — default login: admin / admin

# 3. Create a project in the dashboard:
#    - Name: "crm-calendar-microservices"
#    - Key: "crm-calendar-microservices"

# 4. Generate an access token:
#    Administration → Security → Tokens → Generate

# 5. Run the scanner (from project root):
sonar-scanner \
  -Dsonar.host.url=http://localhost:9000 \
  -Dsonar.token=YOUR_TOKEN_HERE \
  -Dproject.settings=ci/sonar-project.properties

# 6. View results at http://localhost:9000/dashboard?id=crm-calendar-microservices
```

### Configuration

SonarQube is configured via `ci/sonar-project.properties`:

- **Sources:** All code under `services/`
- **Exclusions:** Test files, `__pycache__`, static assets, templates
- **Coverage:** Picks up `coverage.xml` files produced by unit tests
- **Quality gate:** Blocks pipeline if new code has bugs, vulnerabilities, <80% coverage, or >3% duplication (configurable in the SonarQube dashboard)

### Design Decisions

| Decision | Rationale |
|----------|-----------|
| **Self-hosted (Docker)** | Free Community Edition, full control over data, runs on the same infrastructure as the app. No external dependency on SonarCloud. |
| **Separate Compose file** | `ci/docker-compose.sonarqube.yml` keeps SonarQube isolated from the application stack. It's dev tooling, not part of the app — shouldn't start with `docker compose up`. |
| **Quality gate blocks pipeline** | Code quality is a gate, not a suggestion. If SonarQube detects bugs or insufficient coverage on new code, the pipeline stops. This prevents technical debt from accumulating. |
| **Coverage pass-through** | Unit test jobs produce `coverage.xml` → SonarQube picks them up in the next stage. No need to run tests twice. |

---

## Security Scanning (Trivy)

> **Added in iteration-testing branch — February 2026**

Trivy provides two layers of security scanning in the CI pipeline:

### Two-Layer Scanning

| Layer | Command | What It Catches | When It Runs |
|-------|---------|----------------|--------------|
| **Code/Dependency Scan** | `trivy fs ./services/` | Vulnerable Python packages in `requirements.txt`, known CVE patterns in source code | Every branch (Stage 1b) |
| **Image Scan** | `trivy image <image>` | OS-level vulnerabilities (openssl, libc, etc.), base image CVEs, runtime dependencies not in requirements.txt | `main` only after build (Stage 6a) |

> **Why both?** Code scanning catches issues early (before images are built), saving CI time. Image scanning catches different issues — OS packages in the `python:3.11-slim` base image, system libraries installed via `apt-get`, and dependencies that are only present in the built container. Together they provide defense in depth.

### Configuration

Trivy is configured via `ci/.trivy.yaml`:

| Setting | Value | Rationale |
|---------|-------|-----------|
| **Severity** | `CRITICAL` | Only CRITICAL vulnerabilities block the pipeline |
| **Exit code** | `1` | Non-zero exit = pipeline fails |
| **Ignore unfixed** | `true` | Don't fail on CVEs with no available patch — nothing actionable |
| **Format** | `table` (console) + `json` (artifacts) | Human-readable in CI logs, machine-readable for dashboards |

### Running Trivy Locally

```bash
# Scan dependencies (filesystem scan)
trivy fs ./services/

# Scan a built Docker image
docker compose build auth-service
trivy image crm_auth_service:latest

# Scan with full details (HIGH + CRITICAL)
trivy fs --severity HIGH,CRITICAL ./services/
```

---

## Security Scanning (Aikido)

> **Added in iteration-testing branch — February 2026**

[Aikido Security](https://www.aikido.dev/) provides comprehensive application security scanning via its CI/CD API client. It runs **twice** in the pipeline at different stages for different purposes.

### Two-Stage Aikido Strategy

| | Stage 3 — Source Scan | Stage 6b — Release Gate |
|---|---|---|
| **When** | Before build (saves CI time if it fails) | After build + integration tests |
| **Purpose** | Fail-fast gate — skip Stages 4–7 if security issues found | Final security gate + release registration |
| **Scans source code (SAST)** | ✅ | ✅ |
| **Scans dependencies (SCA)** | ✅ | ✅ |
| **Detects secrets** | ✅ | ✅ |
| **Scans IaC (Dockerfiles, Compose)** | ✅ | ✅ |
| **Scans container images** | ❌ (not built yet) | ✅ (if registry access configured) |
| **Registers release for monitoring** | ❌ | ✅ |
| **Continuous CVE alerting** | ❌ | ✅ (alerts post-deploy) |

> **Why run Aikido twice?** Stage 3 is a **cost-saving early gate** — if it catches a vulnerability, you skip ~10 min of build + integration + image scanning. Stage 6b is a **security assurance final gate** that also registers the release for **continuous monitoring**. If a new CVE is published next week affecting your deployed dependencies, Aikido alerts you via its dashboard. Trivy (a point-in-time scanner) cannot do this.

### Aikido vs Trivy — Complementary Coverage

| Capability | Trivy | Aikido |
|-----------|:-----:|:------:|
| Dependency CVEs (SCA) | ✅ | ✅ (different DB) |
| OS-level image CVEs | ✅ | ✅ (via registry) |
| SAST (code analysis) | ❌ | ✅ |
| Secrets detection | ❌ | ✅ |
| IaC misconfiguration | ❌ | ✅ |
| Continuous monitoring | ❌ | ✅ |
| Offline / free | ✅ | ❌ (API quota) |
| Runs on feature branches | ✅ | Via MR quality gating |

### Configuration

Aikido is configured via GitLab CI/CD variables:

| Variable | Purpose | Protected | Masked |
|----------|---------|:---------:|:------:|
| `AIKIDO_CLIENT_API_KEY` | CI API token ([generate at aikido.dev](https://app.aikido.dev) → CI/CD settings) | No (all branches) | Yes |

> The API key is set to **not protected** so it is available on all branches. While the pipeline stages only run on `main`, this allows Aikido's own GitLab MR quality gating integration to also scan feature branch merge requests.

---

## Technologies Used

| Category | Technology | Purpose |
|----------|-----------|---------|
| **Frontend** | HTMX 1.9.10 | Partial page updates without JavaScript |
| | Alpine.js 3.x | Lightweight reactivity (modals, forms) |
| | Tailwind CSS (CDN) | Utility-first styling |
| | Jinja2 | Server-side templating |
| **Backend** | FastAPI | Async Python web framework |
| | SQLAlchemy 2.0 | Async ORM (asyncpg driver) |
| | Pydantic 2.x | Data validation and serialisation |
| | python-jose | JWT creation and verification (HS256) |
| | passlib + bcrypt | Password hashing |
| | httpx | Async HTTP client (inter-service) |
| **Infrastructure** | Docker Compose 3.8 | Multi-container orchestration |
| | NGINX 1.25 | Reverse proxy, rate limiting, security |
| | PostgreSQL 15 | Relational database (9 tables, triggers) |
| | Redis 7 | Caching + token blacklist (128 MB, LRU) |
| | pytest | Testing framework (417 tests) |

---

## Port Reference

| Port | Service | Access |
|------|---------|--------|
| **80** | NGINX Gateway | **Public** — the only exposed port |
| 5432 | PostgreSQL | Host (dev only) |
| 6379 | Redis | Docker network only |
| 8000 | Frontend | Docker network only |
| 8001 | User DB Access | Docker network only |
| 8002 | Customer DB Access | Docker network only |
| 8003 | Job DB Access | Docker network only |
| 8004 | User BL Service | Docker network only |
| 8005 | Auth Service | Docker network only |
| 8006 | Job BL Service | Docker network only |
| 8007 | Customer BL Service | Docker network only |

---

## Recent Updates

**February 15, 2026** — Comprehensive test audit and improvements:
- **Test coverage increased from 309 to 417 tests** (+108 tests, 35% increase)
- Fixed critical auth bug: `require_role` hierarchy bypass that blocked superadmin from cleanup endpoint
- Added 40 new tests to user-db-access covering previously untested company, organization, audit log, and platform settings endpoints
- Added 16 new tests to job-db-access covering 404 paths, include_history, multi-tenant isolation, and calendar overlap detection
- Added 14 new tests to customer-db-access covering note CRUD endpoints and pagination
- Added 17 new tests to frontend covering login/logout pages, admin portal rendering, and calendar year-boundary navigation
- Added comprehensive error path testing (404s, 503s) across all BL services
- All 417 tests passing with zero failures

**February 13, 2026** — Admin portal enhancements:
- Audit log UI improvements: replaced truncated table with searchable, filterable, expandable card layout
- Added Alpine.js Collapse plugin for smooth expand/collapse animations
- Search bar filters across email, action, resource type, and details
- Dynamic filter dropdowns for actions and resources

---

## License

MIT License
