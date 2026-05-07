"""
Integration test fixtures — self-contained data provisioning.

All test data (organisations, companies, users, employee records) is
provisioned via API calls at session start.  The **only** prerequisite
from the Alembic migration is:

* Database schema (tables, indexes, triggers)
* The ``superadmin`` bootstrap user (superadmin@system.local)
* Platform settings rows

Industry-standard patterns applied
-----------------------------------
* **Idempotent provisioning** — safe to re-run without ``docker compose
  down -v`` between sessions.
* Retry with exponential back-off for rate-limited requests (HTTP 429).
* Session-scoped HTTP client for TCP connection reuse.
* Internal-service API calls for setup; tests themselves exercise the
  BL-layer through the nginx gateway.
* Role-based fixtures: owner, employee, admin, manager, viewer,
  superadmin, and a second-tenant owner (``owner2``).
"""

import os
import time
from collections.abc import Generator
from typing import Any

import httpx
import pytest

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BASE_URL = os.getenv("INTEGRATION_BASE_URL", "http://nginx-gateway")
"""
Base URL for API requests through the nginx gateway.
- CI (Docker network):  http://nginx-gateway
- Local (port-mapped):  http://localhost
"""

# Auto-detect local vs CI mode for internal-service access
_LOCAL_MODE = "localhost" in BASE_URL or "127.0.0.1" in BASE_URL

USER_DB_URL = os.getenv(
    "USER_DB_SERVICE_URL",
    "http://localhost:8001" if _LOCAL_MODE else "http://user-db-access-service:8001",
)
"""
Direct URL for the user-db-access-service (internal, **no auth**).
Used *only* during test-data provisioning — tests use the nginx gateway.
"""

# ── Test credentials ──────────────────────────────────────────────────────
SUPERADMIN_EMAIL = "superadmin@system.local"
SUPERADMIN_PASSWORD = "SuperAdmin123!"

OWNER_EMAIL = "owner@demo.com"
OWNER_PASSWORD = "password123"
EMPLOYEE_EMAIL = "employee@demo.com"
EMPLOYEE_PASSWORD = "password123"
ADMIN_EMAIL = "admin@demo.com"
ADMIN_PASSWORD = "password123"
MANAGER_EMAIL = "manager@demo.com"
MANAGER_PASSWORD = "password123"
VIEWER_EMAIL = "viewer@demo.com"
VIEWER_PASSWORD = "password123"
OWNER2_EMAIL = "owner2@demo.com"
OWNER2_PASSWORD = "password123"

REQUEST_TIMEOUT = 15.0  # generous for CI cold starts

# Retry configuration for rate-limited requests
MAX_RETRIES = 5
RETRY_BACKOFF_BASE = 1.0  # seconds — exponential back-off base
INTER_REQUEST_DELAY = 0.25  # seconds — stay within NGINX 5 r/s auth limit


# ---------------------------------------------------------------------------
# Retry-aware HTTP transport
# ---------------------------------------------------------------------------


class RetryTransport(httpx.BaseTransport):
    """
    HTTP transport with automatic retry on transient errors.

    Retries on:
    * HTTP 429 (Too Many Requests) — rate-limiting by nginx
    * httpx.ReadError / httpx.ConnectError / httpx.RemoteProtocolError —
      transient connection resets that occur when a service has passed its
      Docker healthcheck but its upstream is still warming up.

    Exponential back-off: 1 s → 2 s → 4 s → 8 s → 16 s.
    Also inserts a small inter-request delay to reduce bursts.
    """

    # Network-level errors that are safe to retry
    _TRANSIENT_ERRORS = (
        httpx.ReadError,
        httpx.ConnectError,
        httpx.RemoteProtocolError,
    )

    def __init__(self, transport: httpx.BaseTransport):
        self._transport = transport

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        time.sleep(INTER_REQUEST_DELAY)
        for attempt in range(MAX_RETRIES + 1):
            try:
                response = self._transport.handle_request(request)
            except self._TRANSIENT_ERRORS as exc:
                if attempt < MAX_RETRIES:
                    wait = RETRY_BACKOFF_BASE * (2**attempt)
                    print(
                        f"[RetryTransport] transient error on attempt {attempt + 1}"
                        f" ({exc!r}), retrying in {wait:.1f}s …"
                    )
                    time.sleep(wait)
                    continue
                raise
            if response.status_code != 429:
                return response
            # Consume the body and release the connection before retrying
            response.read()
            response.close()
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_BACKOFF_BASE * (2**attempt))
        return response  # return the 429 if all retries exhausted

    def close(self) -> None:
        self._transport.close()


# ---------------------------------------------------------------------------
# Self-contained test-data provisioning helpers
# ---------------------------------------------------------------------------


def _find_org_by_slug(db: httpx.Client, slug: str) -> int | None:
    """Search the organisations list for *slug*; return its ``id`` or ``None``."""
    resp = db.get("/api/v1/organizations", params={"per_page": 100})
    if resp.status_code == 200:
        for org in resp.json().get("items", []):
            if org.get("slug") == slug:
                return org["id"]
    return None


def _find_user_by_email(db: httpx.Client, email: str) -> int | None:
    """Search the users list for *email*; return its ``id`` or ``None``."""
    resp = db.get("/api/v1/users", params={"limit": 500})
    if resp.status_code == 200:
        for user in resp.json().get("items", []):
            if user.get("email") == email:
                return user["id"]
    return None


def _ensure_org(db: httpx.Client, name: str, slug: str, **kwargs) -> int:
    """Create an organisation via the internal API; on conflict look it up."""
    resp = db.post("/api/v1/organizations", json={"name": name, "slug": slug, **kwargs})
    if resp.status_code == 201:
        return resp.json()["id"]
    if resp.status_code in (409, 422):
        found = _find_org_by_slug(db, slug)
        if found is not None:
            return found
    pytest.fail(f"Cannot create/find org '{slug}': {resp.status_code} — {resp.text}")
    return -1  # unreachable, keeps type-checkers happy


def _ensure_company(db: httpx.Client, name: str, org_id: int, **kwargs) -> int:
    """Create a company via the internal API — no unique constraint expected."""
    resp = db.post(
        "/api/v1/companies",
        json={"name": name, "organization_id": org_id, **kwargs},
    )
    if resp.status_code in (200, 201):
        return resp.json()["id"]
    pytest.fail(f"Cannot create company '{name}': {resp.status_code} — {resp.text}")
    return -1


def _ensure_user(
    db: httpx.Client,
    email: str,
    first_name: str,
    last_name: str,
    password: str,
    role: str,
    owner_id: int | None,
    company_id: int,
    org_id: int,
) -> int:
    """Create a user via the internal API; on email conflict look it up."""
    payload: dict[str, Any] = {
        "email": email,
        "first_name": first_name,
        "last_name": last_name,
        "password": password,
        "role": role,
        "company_id": company_id,
        "organization_id": org_id,
    }
    if owner_id is not None:
        payload["owner_id"] = owner_id
    resp = db.post("/api/v1/users", json=payload)
    if resp.status_code == 201:
        return resp.json()["id"]
    if resp.status_code == 409:
        found = _find_user_by_email(db, email)
        if found is not None:
            return found
    pytest.fail(f"Cannot create/find user '{email}': {resp.status_code} — {resp.text}")
    return -1


# ---------------------------------------------------------------------------
# Permission seeding (idempotent — safe on every run)
# ---------------------------------------------------------------------------

# Default permission sets per role (mirrors DEFAULT_ROLE_PERMISSIONS in
# user-db-access-service/app/models/permission.py).
_ROLE_PERMISSIONS: dict[str, dict[str, bool]] = {
    "manager": {
        "company.view": True,
        "employees.create": True,
        "employees.edit": True,
        "customers.create": True,
        "customers.edit": True,
        "jobs.create": True,
        "jobs.edit": True,
        "jobs.assign": True,
        "jobs.schedule": True,
        "jobs.update_status": True,
        "notes.create": True,
        "notes.edit": True,
    },
    "employee": {
        "company.view": True,
        "customers.create": True,
        "customers.edit": True,
        "jobs.create": True,
        "jobs.edit": True,
        "jobs.update_status": True,
        "notes.create": True,
        "notes.edit": True,
    },
    "viewer": {
        "company.view": True,
    },
}


def _ensure_permissions_seeded(gw: httpx.Client) -> None:
    """Seed default role-based permissions for non-privileged users.

    Uses the nginx gateway with owner credentials to call the BL-layer
    PUT /api/v1/users/{user_id}/permissions endpoint.
    Idempotent: upsert semantics mean existing rows are not lost.
    """
    # Login as owner to get a token
    login_resp = gw.post(
        "/api/v1/auth/login",
        json={"email": OWNER_EMAIL, "password": OWNER_PASSWORD},
    )
    if login_resp.status_code != 200:
        return  # owner can't login — nothing to seed

    token = login_resp.json().get("access_token")
    if not token:
        return
    headers = {"Authorization": f"Bearer {token}"}

    # List users to find IDs for subordinate roles
    users_resp = gw.get("/api/v1/users", headers=headers)
    if users_resp.status_code != 200:
        return
    users_list = users_resp.json().get("items", [])

    email_to_id: dict[str, int] = {}
    for u in users_list:
        email_to_id[u.get("email", "")] = u.get("id")

    for perm_email, perm_role in [
        (MANAGER_EMAIL, "manager"),
        (EMPLOYEE_EMAIL, "employee"),
        (VIEWER_EMAIL, "viewer"),
    ]:
        uid = email_to_id.get(perm_email)
        perms = _ROLE_PERMISSIONS.get(perm_role)
        if uid and perms:
            gw.put(
                f"/api/v1/users/{uid}/permissions",
                json={"permissions": perms},
                headers=headers,
            )


# ---------------------------------------------------------------------------
# Main provisioning entry-point
# ---------------------------------------------------------------------------


def _provision_test_data(gw: httpx.Client) -> None:
    """
    Self-contained test-data provisioning.

    Phase 1  Fast-path — if the owner user can already log in, skip.
    Phase 2  Create organisations → companies → users → employee records
             via the **internal** user-db-access-service (no auth).
    Phase 3  Verify by logging in as the owner through nginx.

    Idempotent: 409 (conflict) responses are handled gracefully.
    """

    # ── Phase 1: fast-path ────────────────────────────────────────────────
    check = gw.post(
        "/api/v1/auth/login",
        json={"email": OWNER_EMAIL, "password": OWNER_PASSWORD},
    )
    data_exists = check.status_code == 200

    if data_exists:
        # Data already exists — still ensure permissions are seeded
        _ensure_permissions_seeded(gw)
        return

    print("\n[conftest] Provisioning integration test data via internal API …")

    db = httpx.Client(base_url=USER_DB_URL, timeout=REQUEST_TIMEOUT)
    try:
        # Verify the internal service is reachable
        try:
            db.get("/api/v1/users", params={"limit": 1}, timeout=5.0)
        except httpx.ConnectError:
            pytest.exit(
                f"Cannot reach user-db-access-service at {USER_DB_URL}. "
                "Ensure the stack is running and the service is healthy.",
                returncode=1,
            )

        # ── Organisations ─────────────────────────────────────────────────
        org1_id = _ensure_org(
            db,
            "Default Organization",
            "default-org",
            billing_email="billing@demoservices.ie",
            billing_plan="professional",
            max_users=50,
            max_customers=500,
        )
        org2_id = _ensure_org(
            db,
            "Second Organization",
            "second-org",
            billing_email="billing@secondorg.ie",
            billing_plan="starter",
            max_users=10,
            max_customers=100,
        )

        # ── Companies ─────────────────────────────────────────────────────
        co1_id = _ensure_company(
            db,
            "Demo Services Ltd.",
            org1_id,
            address="456 Business Park, Dublin",
            phone="+353 1 555 0100",
            email="info@demoservices.ie",
            eircode="D04 AB12",
        )
        co2_id = _ensure_company(
            db,
            "Second Corp.",
            org2_id,
            address="789 Other Road, Cork",
            phone="+353 21 555 0200",
            email="info@secondcorp.ie",
            eircode="T12 CD34",
        )

        # ── Owner (tenant 1) ─────────────────────────────────────────────
        owner_id = _ensure_user(
            db,
            OWNER_EMAIL,
            "Demo",
            "Owner",
            OWNER_PASSWORD,
            "owner",
            None,
            co1_id,
            org1_id,
        )
        # Self-referential FK — owner owns themselves
        db.put(f"/api/v1/users/{owner_id}", json={"owner_id": owner_id})

        # ── Subordinate roles (tenant 1) ──────────────────────────────────
        for email, fn, ln, role in [
            (EMPLOYEE_EMAIL, "Demo", "Employee", "employee"),
            (ADMIN_EMAIL, "Demo", "Admin", "admin"),
            (MANAGER_EMAIL, "Demo", "Manager", "manager"),
            (VIEWER_EMAIL, "Demo", "Viewer", "viewer"),
        ]:
            _ensure_user(
                db,
                email,
                fn,
                ln,
                OWNER_PASSWORD,
                role,
                owner_id,
                co1_id,
                org1_id,
            )

        # ── Owner (tenant 2 — cross-tenant isolation) ─────────────────────
        owner2_id = _ensure_user(
            db,
            OWNER2_EMAIL,
            "Second",
            "Owner",
            OWNER2_PASSWORD,
            "owner",
            None,
            co2_id,
            org2_id,
        )
        db.put(f"/api/v1/users/{owner2_id}", json={"owner_id": owner2_id})

        # ── Employee record (links user table → employee details) ─────────
        emp_id = _find_user_by_email(db, EMPLOYEE_EMAIL)
        if emp_id is not None:
            db.post(
                "/api/v1/employees",
                json={
                    "user_id": emp_id,
                    "owner_id": owner_id,
                    "department": "Operations",
                    "position": "Field Technician",
                    "phone": "+353 85 123 4567",
                    "hourly_rate": 35.50,
                    "skills": "Electrical, Plumbing, Carpentry",
                },
            )  # 409 on re-run is harmless

    finally:
        db.close()

    # ── Seed permissions (uses gateway with owner auth) ─────────────────
    _ensure_permissions_seeded(gw)

    # ── Phase 3: verify ───────────────────────────────────────────────────
    verify = gw.post(
        "/api/v1/auth/login",
        json={"email": OWNER_EMAIL, "password": OWNER_PASSWORD},
    )
    assert verify.status_code == 200, (
        f"Provisioning verification failed — owner login returned "
        f"{verify.status_code}: {verify.text}"
    )
    print("[conftest] Test data provisioned successfully.\n")


# ---------------------------------------------------------------------------
# HTTP client fixture
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def http_client() -> Generator[httpx.Client, None, None]:
    """
    Session-scoped HTTP client with retry-on-429 transport.

    On first use, provisions all test data via internal APIs if needed.
    Reuses TCP connections across all tests for performance.
    """
    transport = RetryTransport(httpx.HTTPTransport(retries=2))
    with httpx.Client(
        base_url=BASE_URL,
        timeout=REQUEST_TIMEOUT,
        follow_redirects=True,
        transport=transport,
    ) as client:
        _provision_test_data(client)
        yield client


# ---------------------------------------------------------------------------
# Auth token helpers & fixtures
# ---------------------------------------------------------------------------


def _login(client: httpx.Client, email: str, password: str) -> dict[str, Any]:
    """Log in and return the token payload.  Raises on failure."""
    resp = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert resp.status_code == 200, (
        f"Login failed for {email}: {resp.status_code} — {resp.text}"
    )
    data = resp.json()
    assert "access_token" in data, f"No access_token in response: {data}"
    return data


# ── Owner ──────────────────────────────────────────────────────────────────


@pytest.fixture(scope="session")
def owner_tokens(http_client: httpx.Client) -> dict[str, str]:
    """Session-scoped owner login tokens."""
    return _login(http_client, OWNER_EMAIL, OWNER_PASSWORD)


@pytest.fixture(scope="session")
def owner_token(owner_tokens: dict[str, str]) -> str:
    """Owner's JWT access token string."""
    return owner_tokens["access_token"]


@pytest.fixture(scope="session")
def owner_user_id(owner_tokens: dict[str, str]) -> int:
    """Owner's user ID from the login response."""
    return owner_tokens["user_id"]


@pytest.fixture(scope="session")
def owner_headers(owner_token: str) -> dict[str, str]:
    """Authorization headers for the owner user."""
    return {
        "Authorization": f"Bearer {owner_token}",
        "Content-Type": "application/json",
    }


# ── Employee ───────────────────────────────────────────────────────────────


@pytest.fixture(scope="session")
def employee_tokens(http_client: httpx.Client) -> dict[str, str]:
    """Session-scoped employee login tokens."""
    return _login(http_client, EMPLOYEE_EMAIL, EMPLOYEE_PASSWORD)


@pytest.fixture(scope="session")
def employee_token(employee_tokens: dict[str, str]) -> str:
    """Employee's JWT access token string."""
    return employee_tokens["access_token"]


@pytest.fixture(scope="session")
def employee_user_id(employee_tokens: dict[str, str]) -> int:
    """Employee's user ID from the login response."""
    return employee_tokens["user_id"]


@pytest.fixture(scope="session")
def employee_headers(employee_token: str) -> dict[str, str]:
    """Authorization headers for the employee user."""
    return {
        "Authorization": f"Bearer {employee_token}",
        "Content-Type": "application/json",
    }


# ── Admin ──────────────────────────────────────────────────────────────────


@pytest.fixture(scope="session")
def admin_tokens(http_client: httpx.Client) -> dict[str, str]:
    """Session-scoped admin login tokens."""
    return _login(http_client, ADMIN_EMAIL, ADMIN_PASSWORD)


@pytest.fixture(scope="session")
def admin_token(admin_tokens: dict[str, str]) -> str:
    """Admin's JWT access token string."""
    return admin_tokens["access_token"]


@pytest.fixture(scope="session")
def admin_headers(admin_token: str) -> dict[str, str]:
    """Authorization headers for the admin user."""
    return {
        "Authorization": f"Bearer {admin_token}",
        "Content-Type": "application/json",
    }


# ── Superadmin ─────────────────────────────────────────────────────────────


@pytest.fixture(scope="session")
def superadmin_tokens(http_client: httpx.Client) -> dict[str, str]:
    """Session-scoped superadmin login tokens."""
    return _login(http_client, SUPERADMIN_EMAIL, SUPERADMIN_PASSWORD)


@pytest.fixture(scope="session")
def superadmin_token(superadmin_tokens: dict[str, str]) -> str:
    """Superadmin's JWT access token string."""
    return superadmin_tokens["access_token"]


@pytest.fixture(scope="session")
def superadmin_user_id(superadmin_tokens: dict[str, str]) -> int:
    """Superadmin's user ID from the login response."""
    return superadmin_tokens["user_id"]


@pytest.fixture(scope="session")
def superadmin_headers(superadmin_token: str) -> dict[str, str]:
    """Authorization headers for the superadmin user."""
    return {
        "Authorization": f"Bearer {superadmin_token}",
        "Content-Type": "application/json",
    }


# ── Manager ────────────────────────────────────────────────────────────────


@pytest.fixture(scope="session")
def manager_tokens(http_client: httpx.Client) -> dict[str, str]:
    """Session-scoped manager login tokens."""
    return _login(http_client, MANAGER_EMAIL, MANAGER_PASSWORD)


@pytest.fixture(scope="session")
def manager_token(manager_tokens: dict[str, str]) -> str:
    """Manager's JWT access token string."""
    return manager_tokens["access_token"]


@pytest.fixture(scope="session")
def manager_headers(manager_token: str) -> dict[str, str]:
    """Authorization headers for the manager user."""
    return {
        "Authorization": f"Bearer {manager_token}",
        "Content-Type": "application/json",
    }


# ── Viewer ─────────────────────────────────────────────────────────────────


@pytest.fixture(scope="session")
def viewer_tokens(http_client: httpx.Client) -> dict[str, str]:
    """Session-scoped viewer login tokens."""
    return _login(http_client, VIEWER_EMAIL, VIEWER_PASSWORD)


@pytest.fixture(scope="session")
def viewer_token(viewer_tokens: dict[str, str]) -> str:
    """Viewer's JWT access token string."""
    return viewer_tokens["access_token"]


@pytest.fixture(scope="session")
def viewer_headers(viewer_token: str) -> dict[str, str]:
    """Authorization headers for the viewer user (read-only role)."""
    return {
        "Authorization": f"Bearer {viewer_token}",
        "Content-Type": "application/json",
    }


# ── Second-tenant owner ───────────────────────────────────────────────────


@pytest.fixture(scope="session")
def owner2_tokens(http_client: httpx.Client) -> dict[str, str]:
    """
    Second-tenant owner login tokens.

    Belongs to a *different* organisation and company from owner@demo.com.
    Used for cross-tenant isolation tests.
    """
    return _login(http_client, OWNER2_EMAIL, OWNER2_PASSWORD)


@pytest.fixture(scope="session")
def owner2_token(owner2_tokens: dict[str, str]) -> str:
    """Second-tenant owner's JWT access token string."""
    return owner2_tokens["access_token"]


@pytest.fixture(scope="session")
def owner2_headers(owner2_token: str) -> dict[str, str]:
    """Authorization headers for the second-tenant owner."""
    return {
        "Authorization": f"Bearer {owner2_token}",
        "Content-Type": "application/json",
    }


# ---------------------------------------------------------------------------
# Health check — fail fast if the stack isn't up
# ---------------------------------------------------------------------------


def pytest_configure(config):
    """
    Verify the stack is reachable before running any tests.

    Called during collection — if nginx doesn't respond, all tests
    are skipped with a clear diagnostic message.
    """
    try:
        resp = httpx.get(f"{BASE_URL}/health", timeout=5.0)
        if resp.status_code != 200:
            pytest.exit(
                f"Stack health check failed: {resp.status_code}. Is docker-compose up?",
                returncode=1,
            )
    except httpx.ConnectError:
        pytest.exit(
            f"Cannot connect to {BASE_URL}. Start the stack with: docker compose up -d",
            returncode=1,
        )
