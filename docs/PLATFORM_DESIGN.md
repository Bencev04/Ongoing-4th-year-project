# Platform Design

**CRM Calendar — Multi-Tenant Workflow Platform**

| | |
|--|--|
| **D00196012** | Tadhg Brady |
| **D00258516** | Bence Veres |

---

## Table of Contents

- [1. Repositories and GitOps Structure](#1-repositories-and-gitops-structure)
- [2. Application Architecture](#2-application-architecture)
- [3. Service Inventory](#3-service-inventory)
- [4. Data Layer](#4-data-layer)
- [5. Authentication and Security Model](#5-authentication-and-security-model)
- [6. Multi-Tenancy — Data Isolation](#6-multi-tenancy--data-isolation)
- [7. Environments and Promotion / Deployment Flow](#7-environments-and-promotion--deployment-flow)
- [8. Continuous Integration Strategy](#8-continuous-integration-strategy)
- [9. Testing — Policies and Procedures](#9-testing--policies-and-procedures)
- [10. Continuous Delivery / Deployment](#10-continuous-delivery--deployment)
- [11. Infrastructure as Code](#11-infrastructure-as-code)
- [12. Observability](#12-observability)
- [13. Security Practices](#13-security-practices)

---

## 1. Repositories and GitOps Structure

Two GitLab repositories separate application development from deployment configuration.

### Repo A — Development Repository

Contains all application source code and CI definitions. This is the primary working repository.

| Contents | Purpose |
|----------|---------|
| Frontend + Backend source code (12 Docker services) | Application logic |
| Dockerfiles (one per service) | Container image builds |
| Unit tests (~417 automated tests across 8 services) | Pre-merge quality gate |
| Integration test suite (`tests/integration/`) | End-to-end flow validation |
| `.gitlab-ci.yml` — 7-stage CI pipeline | Build, test, scan, publish |
| `docker-compose.yml` — full local orchestration | Local development environment |
| SonarQube + Trivy configuration (`ci/`) | Code quality and security scanning |

**Build output:** Versioned container images pushed to a container registry (GitLab CR or Docker Hub), tagged with the commit SHA and `:latest`.

### Repo B — Deployment Repository

Contains only deployment manifests and environment configuration. Updating this repo is what triggers Argo CD to deploy.

| Contents | Purpose |
|----------|---------|
| Kubernetes manifests / Helm charts / Kustomize overlays (`dev/staging/prod`) | Declarative infrastructure |
| Environment configuration (replicas, resources, ingress, config maps) | Per-environment tuning |
| Argo CD application definitions | GitOps deployment source of truth |

### Rationale for Two Repositories

- **Clear audit trails** — deployment history is a clean Git log showing who deployed what and when, without noise from feature commits.
- **Easy rollback** — reverting a manifest commit rolls back the deployment without touching application code.
- **Separation of concerns** — developers work in Repo A; platform operators manage Repo B.
- **Security boundary** — production secrets and cluster credentials never touch the development repo.

---

## 2. Application Architecture

The application follows a **layered microservices** design. Each layer has a clear responsibility and communicates only with the layer directly below it. All backend services are built with **FastAPI** (async Python), **SQLAlchemy 2.0** (asyncpg), and **Pydantic 2.x**.

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
                   │  (11 tables)     │       │  (Caching + Auth)│
                   └──────────────────┘       └──────────────────┘
```

### Layer Responsibilities

| Layer | Services | Responsibility |
|-------|----------|----------------|
| **Gateway** | NGINX (:80) | Single public entry point. Rate limiting, OWASP security headers, gzip compression, request routing. Blocks direct access to DB-access services (`/api/v1/internal/*` returns 403). |
| **Presentation** | Frontend (:8000) | Server-rendered HTML with Jinja2 templates. HTMX for partial-page updates, Alpine.js for interactive components (modals, sidebars, calendar). Tailwind CSS via CDN. |
| **Authentication** | Auth Service (:8005) | Issues/verifies JWT tokens (HS256, 30 min TTL), manages refresh tokens, maintains a Redis token blacklist for instant revocation. Supports superadmin impersonation. |
| **Business Logic** | User BL (:8004), Job BL (:8006), Customer BL (:8007), Admin BL (:8008) | Permission enforcement, tenant isolation via `owner_id`, scheduling conflict detection, data enrichment (merges data from multiple DB services). All requests verified through Auth Service before data access. |
| **Data Access** | User DB (:8001), Customer DB (:8002), Job DB (:8003) | Pure CRUD operations over PostgreSQL. No authentication, no business rules. Only reachable from the internal Docker network. |
| **Caching** | Redis (:6379) | Token blacklist (DB0), user cache (DB1), job cache (DB2), customer cache (DB3), admin cache (DB4). 128 MB max, LRU eviction, AOF persistence. |
| **Storage** | PostgreSQL (:5432) | 11 tables with automatic `updated_at` triggers, full audit trail, and demo seed data. |

### Why Separate BL and DB Layers?

- The data layer can be **replicated or optimised** independently (read replicas, connection pooling) without affecting business rules.
- BL services benefit from **Redis caching** — repeated reads hit the cache, reducing database load.
- Each layer **scales independently** — a spike in job scheduling does not require scaling customer CRUD.
- DB-access services present a **stable internal API** that multiple BL services can consume.

---

## 3. Service Inventory

The platform comprises **12 Docker services** orchestrated via Docker Compose:

| Service | Port | Technology | Role |
|---------|------|------------|------|
| `nginx-gateway` | 80 (public) | NGINX | Reverse proxy, rate limiting, security headers, routing |
| `frontend` | 8000 | FastAPI + Jinja2 + HTMX + Alpine.js | Server-rendered UI, API proxy |
| `auth-service` | 8005 | FastAPI | JWT issue/verify/refresh, token blacklist, impersonation |
| `user-bl-service` | 8004 | FastAPI | User management, roles, invitations, employee records |
| `job-bl-service` | 8006 | FastAPI | Job scheduling, conflict detection, calendar, queue |
| `customer-bl-service` | 8007 | FastAPI | Customer CRUD, customer notes, job enrichment |
| `admin-bl-service` | 8008 | FastAPI | Platform administration (superadmin only), org CRUD, audit trails |
| `user-db-access-service` | 8001 | FastAPI + SQLAlchemy | User/employee database CRUD (internal) |
| `customer-db-access-service` | 8002 | FastAPI + SQLAlchemy | Customer/notes database CRUD (internal) |
| `job-db-access-service` | 8003 | FastAPI + SQLAlchemy | Job/calendar database CRUD (internal) |
| `db` | 5432 | PostgreSQL 15 Alpine | Relational data store |
| `redis` | 6379 | Redis 7 Alpine | Caching and token blacklist |

### Shared Module (`services/shared/common/`)

All backend services import a shared library that provides consistent infrastructure:

| Module | Purpose |
|--------|---------|
| `config.py` | Pydantic `Settings` — service URLs, cache TTLs, secrets (loaded from environment / `.env`) |
| `database.py` | Async SQLAlchemy engine + session factory (`get_async_db` dependency) |
| `redis.py` | Async Redis client with `cache_get` / `cache_set` / `cache_delete` / `cache_delete_pattern` |
| `exceptions.py` | `BaseServiceException` hierarchy auto-mapped to JSON HTTP error responses |
| `schemas.py` | `PaginatedResponse`, `HealthResponse`, `ErrorResponse` base schemas |
| `auth.py` | `CurrentUser`, `require_role`, `require_superadmin`, `verify_tenant_access` dependencies |
| `audit.py` | Fire-and-forget `log_action()` for immutable audit trail entries |

---

## 4. Data Layer

### Database Schema

PostgreSQL 15 with **11 tables** across four domains:

| Domain | Tables | Key Fields |
|--------|--------|------------|
| **Organization** | `organizations` | `id`, `name`, `slug`, `billing_plan`, `max_users`, `max_customers`, `is_active`, `suspended_at` |
| **Tenant / Users** | `companies`, `users`, `employees` | `owner_id` (tenant isolation key), `company_id`, `organization_id`, `role` (superadmin / owner / admin / manager / employee / viewer) |
| **Business Data** | `customers`, `customer_notes`, `jobs`, `job_history` | All scoped by `owner_id`. Jobs support full lifecycle: pending → scheduled → in_progress → completed → cancelled. `job_history` provides field-level audit trail. |
| **Auth** | `refresh_tokens`, `token_blacklist` | Refresh tokens hashed with SHA-256. Blacklist entries keyed by JWT `jti`. Both have expiry-based cleanup. |
| **Platform** | `audit_logs`, `platform_settings` | `audit_logs` records every significant action (JSONB `details`). `platform_settings` is a key-value store for system-wide config. |

All tables use:
- `created_at` / `updated_at` timestamps with automatic triggers.
- Foreign key constraints with appropriate `ON DELETE` cascades.
- Indexed columns for owner lookups, date ranges, and status filters.

### Redis Configuration

| Database | Service | Content |
|----------|---------|---------|
| DB0 | Auth Service | Token blacklist (instant logout) |
| DB1 | User BL Service | User/employee response cache |
| DB2 | Job BL Service | Job/calendar response cache |
| DB3 | Customer BL Service | Customer/notes response cache |
| DB4 | Admin BL Service | Admin response cache |

Configuration: 128 MB max memory, LRU eviction policy, AOF persistence enabled.

---

## 5. Authentication and Security Model

### JWT Token Flow

1. User submits credentials to `POST /api/v1/auth/login`.
2. Auth Service forwards to User DB Access `POST /internal/authenticate` for bcrypt verification.
3. On success, Auth Service issues:
   - **Access token** (JWT HS256, 30-minute TTL) containing `user_id`, `email`, `role`, `owner_id`, `company_id`, `jti`.
   - **Refresh token** (random, hashed and stored in DB).
4. Browser stores both tokens in `localStorage`. The `authFetch()` helper auto-attaches the Bearer header on every request.
5. On token expiry, `authFetch()` silently calls `POST /api/v1/auth/refresh` and retries the original request.

### Request Verification

Every BL service verifies every incoming request by calling `POST /api/v1/auth/verify` on the Auth Service. The Auth Service:
- Decodes the JWT and validates the signature.
- Checks the `jti` against the Redis blacklist (instant revocation).
- Returns the user context (`user_id`, `owner_id`, `role`) or rejects with 401.

### Superadmin Impersonation

Superadmins can impersonate any user via `POST /api/v1/auth/impersonate`, creating a 15-minute shadow token that includes `acting_as` and `impersonator_id` claims. All actions during impersonation are logged in the audit trail.

### Rate Limiting (NGINX)

| Endpoint Pattern | Rate Limit | Purpose |
|------------------|-----------|---------|
| `/api/v1/auth/*` | 5 req/s per IP, burst 10 | Brute-force login protection |
| `/api/v1/*` (all other) | 30 req/s per IP, burst 20 | General abuse prevention |
| Global connection limit | 100 per IP | Connection exhaustion prevention |

---

## 6. Multi-Tenancy — Data Isolation

The platform uses a **shared-database, shared-schema** multi-tenancy model. Every data-bearing table includes an `owner_id` column that references the business owner's user ID.

### How `owner_id` Works

```
  organizations
       │
  companies (organization_id → organizations.id)
       │
  users (company_id → companies.id)
       │ owner_id = user.id (for owners, self-referential)
       │ owner_id = owner's user.id (for employees)
       │
  ┌────┴────────────┬─────────────┐
  │                 │             │
  customers      employees      jobs
  (owner_id)     (owner_id)    (owner_id)
       │
  customer_notes
```

- The **owner's** `owner_id` is set to their own `id` (self-referential).
- Every **employee** inherits the owner's `owner_id`.
- All **customers**, **jobs**, and **notes** are stamped with `owner_id`.
- Every SQL query includes `WHERE owner_id = <value from JWT>`.
- Superadmins have `owner_id = NULL` — they operate above the tenant level.

This ensures that Tenant A can never see or modify Tenant B's data, even though both share the same database.

### Role Hierarchy

| Role | Scope | Capabilities |
|------|-------|-------------|
| `superadmin` | Platform-wide | Manage organizations, impersonate users, view audit logs, platform settings |
| `owner` | Own tenant | Full control over company, employees, customers, jobs |
| `admin` | Own tenant | Manage employees and customers, cannot delete company |
| `manager` | Own tenant | Manage jobs and schedules, limited employee management |
| `employee` | Own tenant | View assigned jobs, update job status |
| `viewer` | Own tenant | Read-only access to assigned data |

---

## 7. Environments and Promotion / Deployment Flow

Three major environments with distinct responsibilities:

### Development (Local — Docker Compose)

- Full 12-service stack running locally via `docker-compose up -d --build`.
- Single command startup on port 80 (NGINX gateway).
- PostgreSQL with seed data for immediate testing (demo credentials: `owner@demo.com` / `password123`).
- Ideal for feature development, debugging, and rapid iteration.

### Staging (XOA — On-Premises)

- Pre-production testing environment hosted on XOA infrastructure.
- Receives deployments automatically after the CI pipeline passes on merges to `main`.
- Used for:
  - Integration and regression testing.
  - Performance and usability testing.
  - User Acceptance Testing (UAT) with real users.

### Production (AWS — Cloud)

- Final customer-facing environment hosted on AWS.
- Only promoted after the staging environment has been cleared.
- Managed via Argo CD watching the deployment repository.
- Infrastructure provisioned and version-controlled with Terraform.

### Promotion Flow

```
  Developer pushes feature branch
       │
       ▼
  Merge Request opened
       │
       ▼
  ┌─────────────────────────────────────────────────────┐
  │  CI Pipeline (Stages 1-3)                           │
  │  1. Unit Tests (8 parallel jobs, ~417 tests)        │
  │  2. SonarQube Code Quality Analysis                 │
  │  3. Trivy Security Scan (dependencies)              │
  └────────────────────────┬────────────────────────────┘
                           │  MR approved + merged to main
                           ▼
  ┌─────────────────────────────────────────────────────┐
  │  CI Pipeline (Stages 4-7) — main branch only        │
  │  4. Build & push container images (tagged SHA)      │
  │  5. Trivy Image Scan (OS-level vulnerabilities)     │
  │  6. Integration Tests (full stack in CI)             │
  │  7. Trigger Deployment Repo (manual gate)            │
  └────────────────────────┬────────────────────────────┘
                           │  Manual approval
                           ▼
  ┌─────────────────────────────────────────────────────┐
  │  Deploy to Staging (XOA)                             │
  │  • Smoke tests run automatically                    │
  │  • UAT conducted with test users                    │
  └────────────────────────┬────────────────────────────┘
                           │  UAT passed
                           ▼
  ┌─────────────────────────────────────────────────────┐
  │  Update Deployment Repo for Production               │
  │  • Argo CD detects manifest change                  │
  │  • Deploys to AWS                                    │
  │  • Post-deployment smoke tests                      │
  └─────────────────────────────────────────────────────┘
```

---

## 8. Continuous Integration Strategy

The CI pipeline is defined in `.gitlab-ci.yml` and hosted on `gitlab.comp.dkit.ie`. It is split across two repositories — Repo A (development) handles testing and image building; Repo B (deployment) handles deployment triggers.

### Pipeline Stages

```
Feature/MR branches (~5-7 min):

  ┌──────────┐    ┌───────────┐    ┌────────────┐
  │ 1. Unit  │───▶│ 2. Sonar- │───▶│ 3. Trivy   │
  │  Tests   │    │   Qube    │    │  Code Scan │
  └──────────┘    └───────────┘    └────────────┘
  (8 parallel)    (~1-2 min)       (~1 min)

main branch — full pipeline (~15-20 min):

  ┌──────┐  ┌──────┐  ┌──────┐  ┌──────┐  ┌──────┐  ┌──────┐  ┌──────────┐
  │ Unit │─▶│Sonar │─▶│Trivy │─▶│Build │─▶│Trivy │─▶│Integ │─▶│  Deploy  │
  │Tests │  │ Qube │  │ Code │  │Images│  │Image │  │Tests │  │ (manual) │
  └──────┘  └──────┘  └──────┘  └──────┘  └──────┘  └──────┘  └──────────┘
```

### Branch Rules

| Branch / Event | Stages That Run |
|----------------|-----------------|
| Any **merge request** | 1 (test) → 2 (quality) → 3 (scan:code) |
| Push to **`develop`** | 1 (test) → 2 (quality) → 3 (scan:code) |
| Push to **`main`** | All 7 stages |
| Any other branch | Pipeline not triggered |

### Stage Details

| Stage | What It Does | Failure Behaviour |
|-------|-------------|-------------------|
| **1. Unit Tests** | 8 parallel pytest jobs (one per testable service). DB-access services use Postgres service containers; BL services use HTTP mocks. Produces Cobertura `coverage.xml` artifacts. | Merge blocked |
| **2. SonarQube** | Sends source + coverage to SonarQube. Enforces quality gate (coverage thresholds, code smells, bugs). | Merge blocked |
| **3. Trivy Code Scan** | Scans all `requirements.txt` files for known CVEs. CRITICAL = pipeline fail. JSON report artifact. | Merge blocked |
| **4. Build Images** | Docker-in-Docker build of all 9 Dockerfiles. Tags with commit SHA + `:latest`. Pushes to container registry. | Pipeline fail |
| **5. Trivy Image Scan** | Pulls built images and scans for OS-level vulnerabilities. | Pipeline fail |
| **6. Integration Tests** | Spins up entire Docker Compose stack inside CI, waits for health checks, runs `tests/integration/` suite. Service logs captured as artifacts. | Pipeline fail |
| **7. Deploy Trigger** | Manual gate (▶️ button). Sends `curl` POST to deployment repo trigger URL, passing image tag and commit SHA. | Manual retry |

---

## 9. Testing — Policies and Procedures

Testing is structured across multiple levels to ensure comprehensive coverage.

### Unit Testing

Unit tests are the first gate in the CI pipeline and focus on individual functions, services, and business logic.

**Scope:**
- Creation and validation for jobs, clients, and users.
- Role-based access control checks (owner, admin, employee, viewer, superadmin).
- Scheduling and conflict detection logic.
- Tenant isolation enforcement (owner_id filtering).
- Field translation between public and internal formats.

**Methodologies:**
- **Boundary Value Analysis (BVA):** Testing edge cases such as job dates at boundaries, maximum field lengths, and pagination limits.
- **Positive and negative test cases:** Validating both successful operations and expected error responses (e.g., booking a job in the past should fail, accessing another tenant's data should return 403).
- **Success criteria:** Each test asserts a valid response and correct state — e.g., creating a job returns the job with correct fields, deleting a non-existent resource returns 404.

**Current coverage:** ~417 automated tests across 8 services, run in parallel during CI.

| Test Job | Service | Database |
|----------|---------|----------|
| `test:auth-service` | Auth | In-memory SQLite |
| `test:user-db-access-service` | User DB Access | Postgres (CI service container) |
| `test:customer-db-access-service` | Customer DB Access | Postgres (CI service container) |
| `test:job-db-access-service` | Job DB Access | Postgres (CI service container) |
| `test:user-bl-service` | User BL | HTTP mocked |
| `test:customer-bl-service` | Customer BL | HTTP mocked |
| `test:job-bl-service` | Job BL | HTTP mocked |
| `test:frontend` | Frontend | HTTP mocked |

### Integration Testing

Integration tests validate interconnectivity between services and components. The full Docker Compose stack is spun up and tests run against the live service mesh.

**Scope:**
- End-to-end authentication flow: login → verify → refresh → logout.
- Cross-service data operations: creating a job that references a customer and an employee from different services.
- NGINX routing validation: correct services receive correct requests.
- Tenant isolation across services: ensuring one tenant's actions cannot affect another.
- Admin flow: superadmin operations, impersonation, audit trail verification.

**Test suites (`tests/integration/`):**

| Suite | Coverage |
|-------|----------|
| `test_auth_flow.py` | Login, verify, refresh, logout |
| `test_user_flow.py` | User and employee listing |
| `test_customer_flow.py` | Customer CRUD + notes |
| `test_job_flow.py` | Job CRUD, calendar, queue |
| `test_admin_flow.py` | Superadmin operations |
| `test_impersonation_e2e.py` | Superadmin impersonation flow |
| `test_e2e_smoke.py` | Health checks, full business path, NGINX routing |

**Success criteria:** Valid HTTP responses returning from downstream services; data consistency across service boundaries; no data leakage between tenants.

### User Acceptance Testing (UAT)

UAT takes place in the **staging environment** (XOA). The site is made accessible to representative users to validate usability and gather feedback.

**Scope:**
- Test end-to-end workflows (registration → company setup → employee invite → customer creation → job scheduling → calendar view).
- Monitor and improve user experience and usability.
- Users are requested to test and give feedback on proposed changes before production deployment.

**User criteria — three test groups:**

| Group | Profile | Purpose |
|-------|---------|---------|
| **Beginner** | No prior experience with CRM/scheduling tools | Validates discoverability and onboarding |
| **Novice** | Some experience with similar tools | Validates intuitiveness and learning curve |
| **Expert** | Experienced with CRM/scheduling platforms | Validates efficiency and power-user workflows |

Each group is asked to achieve the same set of tasks, which are monitored. Feedback is collected from each group to ensure strong UX design and that every element of the site is usable and accessible.

### Additional Tests (Production Quality)

| Test Type | Tool | When | Purpose |
|-----------|------|------|---------|
| **Smoke tests** | pytest | After every staging/prod deployment | Basic health endpoints + critical business paths |
| **Load testing** | k6 / Locust | Against staging | Capture latency, throughput, and error rates under load |
| **Resilience tests** | Manual / scripted | Against staging | Deliberately restart pods/services and verify recovery, self-healing, and data consistency |

---

## 10. Continuous Delivery / Deployment

### GitOps Process

Argo CD is the deployment engine, following GitOps principles:

1. Argo CD watches the **deployment repository** (Repo B).
2. Any merge to `main` in the deployment repo is automatically detected.
3. Argo CD compares the desired state (repo manifests) with the actual state (cluster).
4. Necessary changes are applied to bring the environment in line with the repo.
5. Argo CD continuously monitors for drift and self-heals.

### Deployment Strategy

At least one of the following strategies will be implemented:

**Option 1 — Blue/Green Deployment**

- Two identical versions of the application run side by side.
- Traffic is switched between the blue (current) and green (new) versions via ingress configuration.
- Instant rollback by switching traffic back to the previous version.
- Higher resource cost (double the infrastructure during deployment).

**Option 2 — Canary Deployment**

- New version receives a small percentage of traffic initially (e.g., 5%).
- Traffic is gradually shifted: 5% → 25% → 50% → 100%.
- Automated rollback if error rates or latency exceed defined thresholds.
- Lower risk — issues are caught before full rollout.
- Requires robust observability to detect anomalies early.

---

## 11. Infrastructure as Code

**Terraform** is used to provision and version-control all cloud infrastructure. All infrastructure changes go through the same Git workflow as application code — pull request, review, merge.

### AWS Resources Provisioned by Terraform

| Resource | Purpose |
|----------|---------|
| **VPC** | Isolated virtual network for the production environment |
| **Subnets** | Public subnets for load balancers/ingress; private subnets for application workloads and databases |
| **Security Groups** | Strict inbound rules — only the ingress controller is publicly exposed. Internal services communicate on private subnets only |
| **IAM Roles** | Least-privilege roles for CI/CD tools, Argo CD, and application services |
| **RDS (PostgreSQL)** | Managed PostgreSQL instance with automated backups, encryption at rest, and private subnet placement |
| **EKS / Kubernetes** | Managed Kubernetes cluster for container orchestration |

### Key Principles

- **Idempotent:** Running `terraform apply` multiple times produces the same result.
- **State management:** Terraform state stored remotely (S3 + DynamoDB locking) for team collaboration.
- **Environment parity:** Dev, staging, and production use the same Terraform modules with different variable files.

---

## 12. Observability

Observability tooling monitors the health of every deployment. The primary stack is the **Elastic Stack** (ELK).

### Logging

- All services emit **structured JSON logs** (NGINX uses `json_combined` log format; Python services use structured logging).
- Logs are aggregated into a central collection point via **Logstash**.
- Logs are searchable via **Elasticsearch**, enabling rapid issue tracking and root-cause analysis.
- Log fields include: timestamp, service name, request ID (`X-Request-ID` from NGINX), user context, and error details.

### Metrics and Dashboards

- **Kibana dashboards** provide an overview of platform health:
  - Service uptime and availability.
  - CPU, memory, and network utilisation per service.
  - Request latency (p50, p95, p99) per endpoint.
  - Error rates by service and status code.
- Reports are generated to outline **SLI/SLA metrics** based on pre-set targets:

| Metric (SLI) | Target (SLA) |
|---------------|-------------|
| Availability | ≥ 99.5% uptime |
| API response time (p95) | ≤ 500 ms |
| Error rate | < 1% of requests |
| Login success rate | ≥ 99% |

### Alerting

Alerts are configured to notify relevant parties via email when:

- Any service goes down or fails health checks.
- SLI/SLA thresholds are trending off course.
- Services are running out of resources (CPU/memory) — enabling proactive scaling before performance degrades.
- Error rate spikes above threshold.
- Sustained high latency detected.

---

## 13. Security Practices

### Secrets Management

| Principle | Implementation |
|-----------|---------------|
| **No secrets in Git** | All secrets are injected via environment variables. `.env` files are `.gitignore`d. |
| **CI secrets** | GitLab protected and masked CI/CD variables (SonarQube tokens, registry credentials, deploy tokens). |
| **Runtime secrets** | AWS Secrets Manager or Kubernetes External Secrets for production. Docker Compose environment variables for local development. |
| **Password hashing** | bcrypt with 12 rounds for all user passwords. |
| **Token security** | Refresh tokens stored as SHA-256 hashes. Access tokens use unique `jti` for revocation. |

### Access Control and Network Security

| Layer | Control |
|-------|---------|
| **API Gateway** | NGINX is the single public entry point. All internal services expose only Docker-internal ports. |
| **DB-access services** | Never exposed externally. NGINX returns 403 on `/api/v1/internal/*`. |
| **Database** | PostgreSQL and Redis are not publicly accessible — `expose` only (no `ports` mapping in production). |
| **Authentication** | Every BL service request is verified via the Auth Service. No service trusts tokens independently. |
| **Tenant isolation** | `owner_id` enforced at the application layer on every query. Superadmin operations logged in `audit_logs`. |
| **IAM** | Least-privilege IAM roles for CI/CD tools. No broad wildcard permissions. |
| **Security headers** | OWASP baseline: `X-Frame-Options`, `X-Content-Type-Options`, `X-XSS-Protection`, `Strict-Transport-Security`, `Referrer-Policy`, `Permissions-Policy`. |
| **Security scanning** | Trivy scans for CVEs in both Python dependencies and Docker images. CRITICAL findings block the pipeline. |
| **SonarQube** | Static code analysis for bugs, code smells, and security hotspots. Quality gate enforced on every merge. |

---

**Last Updated:** February 2026
