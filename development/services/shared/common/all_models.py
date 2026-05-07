"""
Centralized model imports for Alembic autogenerate.

This module imports every SQLAlchemy model from all DB-access services
so that ``Base.metadata`` is fully populated when Alembic inspects it.

**Only used by the migration runner** — application services do NOT
import this module at runtime.

The import paths correspond to the container layout defined in
``services/migration-runner/Dockerfile``:

    /app/
      shared/common/          -> common.*
      app_auth/models/        -> app_auth.models.auth
      app_user/models/        -> app_user.models.user
      app_customer/models/    -> app_customer.models.customer
      app_job/models/         -> app_job.models.job
"""

# ── Auth service models ──────────────────────────────────────────────────────
from app_auth.models.auth import RefreshToken, TokenBlacklist  # noqa: F401

# ── Customer service models ──────────────────────────────────────────────────
from app_customer.models.customer import Customer, CustomerNote  # noqa: F401

# ── Job service models ───────────────────────────────────────────────────────
from app_job.models.job import Job, JobHistory, JobPriority, JobStatus  # noqa: F401

# ── User service models ─────────────────────────────────────────────────────
from app_user.models.user import (  # noqa: F401
    AuditLog,
    Company,
    Employee,
    Organization,
    PlatformSetting,
    User,
    UserRole,
)
