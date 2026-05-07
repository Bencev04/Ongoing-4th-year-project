"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-03-03

Creates the full CRM Calendar database schema, triggers, functions,
and bootstrap data (superadmin + platform settings).

This migration manages the full CRM Calendar database schema.
Demo/seed data is NOT included here — it lives in
``scripts/seed-demo-data.sql`` and is mounted separately in dev/CI.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # Extensions
    # ------------------------------------------------------------------
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')

    # ------------------------------------------------------------------
    # 1. organizations
    # ------------------------------------------------------------------
    op.create_table(
        "organizations",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(100), unique=True, nullable=False),
        sa.Column("billing_email", sa.String(255), nullable=True),
        sa.Column("billing_plan", sa.String(50), server_default="free", nullable=False),
        sa.Column("max_users", sa.Integer, server_default="50", nullable=False),
        sa.Column("max_customers", sa.Integer, server_default="500", nullable=False),
        sa.Column(
            "is_active", sa.Boolean, server_default=sa.text("true"), nullable=False
        ),
        sa.Column("suspended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("suspended_reason", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "billing_plan IN ('free', 'starter', 'professional', 'enterprise')",
            name="valid_billing_plan",
        ),
    )
    op.create_index("idx_organizations_slug", "organizations", ["slug"])
    op.create_index("idx_organizations_is_active", "organizations", ["is_active"])

    # ------------------------------------------------------------------
    # 2. companies
    # ------------------------------------------------------------------
    op.create_table(
        "companies",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "organization_id",
            sa.Integer,
            sa.ForeignKey("organizations.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("address", sa.Text, nullable=True),
        sa.Column("phone", sa.String(50), nullable=True),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("eircode", sa.String(10), nullable=True),
        sa.Column("logo_url", sa.String(500), nullable=True),
        sa.Column(
            "is_active", sa.Boolean, server_default=sa.text("true"), nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
    )
    op.create_index("idx_companies_name", "companies", ["name"])

    # ------------------------------------------------------------------
    # 3. users
    # ------------------------------------------------------------------
    op.create_table(
        "users",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("email", sa.String(255), unique=True, nullable=False),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("first_name", sa.String(255), nullable=False),
        sa.Column("last_name", sa.String(255), nullable=False),
        sa.Column("phone", sa.String(50), nullable=True),
        sa.Column("role", sa.String(50), server_default="employee", nullable=False),
        sa.Column(
            "is_active", sa.Boolean, server_default=sa.text("true"), nullable=False
        ),
        sa.Column(
            "owner_id",
            sa.Integer,
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "company_id",
            sa.Integer,
            sa.ForeignKey("companies.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "organization_id",
            sa.Integer,
            sa.ForeignKey("organizations.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "role IN ('superadmin', 'owner', 'admin', 'manager', 'employee', 'viewer')",
            name="valid_role",
        ),
    )
    op.create_index("idx_users_email", "users", ["email"])
    op.create_index("idx_users_owner_id", "users", ["owner_id"])
    op.create_index("idx_users_company_id", "users", ["company_id"])
    op.create_index("idx_users_organization_id", "users", ["organization_id"])

    # ------------------------------------------------------------------
    # 4. employees
    # ------------------------------------------------------------------
    op.create_table(
        "employees",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "user_id",
            sa.Integer,
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "owner_id",
            sa.Integer,
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("department", sa.String(100), nullable=True),
        sa.Column("position", sa.String(100), nullable=True),
        sa.Column("phone", sa.String(50), nullable=True),
        sa.Column("hire_date", sa.Date, nullable=True),
        sa.Column("hourly_rate", sa.Numeric(10, 2), nullable=True),
        sa.Column("skills", sa.Text, nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column(
            "is_active", sa.Boolean, server_default=sa.text("true"), nullable=True
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "user_id", "owner_id", name="employees_user_id_owner_id_key"
        ),
    )
    op.create_index("idx_employees_owner_id", "employees", ["owner_id"])

    # ------------------------------------------------------------------
    # 5. customers
    # ------------------------------------------------------------------
    op.create_table(
        "customers",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("owner_id", sa.Integer, nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("phone", sa.String(50), nullable=True),
        sa.Column("address", sa.Text, nullable=True),
        sa.Column("eircode", sa.String(10), nullable=True),
        sa.Column("company_name", sa.String(255), nullable=True),
        sa.Column(
            "is_active", sa.Boolean, server_default=sa.text("true"), nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
    )
    op.create_index("idx_customers_owner_id", "customers", ["owner_id"])
    op.create_index("idx_customers_email", "customers", ["email"])

    # ------------------------------------------------------------------
    # 6. customer_notes
    # ------------------------------------------------------------------
    op.create_table(
        "customer_notes",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "customer_id",
            sa.Integer,
            sa.ForeignKey("customers.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("created_by_id", sa.Integer, nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
    )
    op.create_index("idx_customer_notes_customer_id", "customer_notes", ["customer_id"])

    # ------------------------------------------------------------------
    # 7. jobs
    # ------------------------------------------------------------------
    op.create_table(
        "jobs",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("customer_id", sa.Integer, nullable=True),
        sa.Column("owner_id", sa.Integer, nullable=False),
        sa.Column("assigned_employee_id", sa.Integer, nullable=True),
        sa.Column("created_by_id", sa.Integer, nullable=False),
        sa.Column("status", sa.String(50), server_default="pending", nullable=False),
        sa.Column("priority", sa.String(50), server_default="normal", nullable=False),
        sa.Column("start_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("end_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "all_day", sa.Boolean, server_default=sa.text("false"), nullable=False
        ),
        sa.Column("location", sa.Text, nullable=True),
        sa.Column("eircode", sa.String(10), nullable=True),
        sa.Column("estimated_duration", sa.Integer, nullable=True),
        sa.Column("actual_duration", sa.Integer, nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("color", sa.String(20), nullable=True),
        sa.Column(
            "is_recurring", sa.Boolean, server_default=sa.text("false"), nullable=False
        ),
        sa.Column("recurrence_rule", sa.String(500), nullable=True),
        sa.Column(
            "parent_job_id",
            sa.Integer,
            sa.ForeignKey("jobs.id"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'scheduled', 'in_progress', 'completed', 'cancelled', 'on_hold')",
            name="valid_status",
        ),
        sa.CheckConstraint(
            "priority IN ('low', 'normal', 'high', 'urgent')",
            name="valid_priority",
        ),
        sa.CheckConstraint(
            "(start_time IS NULL AND end_time IS NULL) OR (end_time > start_time)",
            name="valid_time_range",
        ),
    )
    op.create_index("idx_jobs_owner_id", "jobs", ["owner_id"])
    op.create_index("idx_jobs_customer_id", "jobs", ["customer_id"])
    op.create_index("idx_jobs_assigned_employee_id", "jobs", ["assigned_employee_id"])
    op.create_index("idx_jobs_status", "jobs", ["status"])
    op.create_index("idx_jobs_start_time", "jobs", ["start_time"])
    op.create_index("idx_jobs_date_range", "jobs", ["start_time", "end_time"])

    # ------------------------------------------------------------------
    # 8. job_history
    # ------------------------------------------------------------------
    op.create_table(
        "job_history",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "job_id",
            sa.Integer,
            sa.ForeignKey("jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("changed_by_id", sa.Integer, nullable=False),
        sa.Column("change_type", sa.String(50), nullable=False),
        sa.Column("field_changed", sa.String(100), nullable=True),
        sa.Column("old_value", sa.Text, nullable=True),
        sa.Column("new_value", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
    )
    op.create_index("idx_job_history_job_id", "job_history", ["job_id"])

    # ------------------------------------------------------------------
    # 9. refresh_tokens
    # ------------------------------------------------------------------
    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer, nullable=False),
        sa.Column("owner_id", sa.Integer, nullable=False),
        sa.Column("token_hash", sa.String(64), unique=True, nullable=False),
        sa.Column("device_info", sa.String(255), nullable=True),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "is_revoked", sa.Boolean, server_default=sa.text("false"), nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
    )
    op.create_index("idx_refresh_tokens_user_id", "refresh_tokens", ["user_id"])
    op.create_index("idx_refresh_tokens_token_hash", "refresh_tokens", ["token_hash"])
    op.create_index("idx_refresh_tokens_expires_at", "refresh_tokens", ["expires_at"])

    # ------------------------------------------------------------------
    # 10. token_blacklist
    # ------------------------------------------------------------------
    op.create_table(
        "token_blacklist",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("jti", sa.String(36), unique=True, nullable=False),
        sa.Column("user_id", sa.Integer, nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
    )
    op.create_index("idx_token_blacklist_jti", "token_blacklist", ["jti"])
    op.create_index("idx_token_blacklist_expires_at", "token_blacklist", ["expires_at"])

    # ------------------------------------------------------------------
    # 11. audit_logs
    # ------------------------------------------------------------------
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column(
            "timestamp",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "actor_id",
            sa.Integer,
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("actor_email", sa.String(255), nullable=True),
        sa.Column("actor_role", sa.String(50), nullable=True),
        sa.Column(
            "impersonator_id",
            sa.Integer,
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "organization_id",
            sa.Integer,
            sa.ForeignKey("organizations.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("resource_type", sa.String(100), nullable=True),
        sa.Column("resource_id", sa.String(100), nullable=True),
        sa.Column(
            "details", sa.JSON, server_default=sa.text("'{}'::jsonb"), nullable=True
        ),
        sa.Column("ip_address", sa.String(45), nullable=True),
    )
    op.create_index("idx_audit_logs_timestamp", "audit_logs", ["timestamp"])
    op.create_index("idx_audit_logs_actor_id", "audit_logs", ["actor_id"])
    op.create_index("idx_audit_logs_organization_id", "audit_logs", ["organization_id"])
    op.create_index("idx_audit_logs_action", "audit_logs", ["action"])
    op.create_index(
        "idx_audit_logs_resource", "audit_logs", ["resource_type", "resource_id"]
    )

    # ------------------------------------------------------------------
    # 12. platform_settings
    # ------------------------------------------------------------------
    op.create_table(
        "platform_settings",
        sa.Column("key", sa.String(100), primary_key=True, nullable=False),
        sa.Column(
            "value", sa.JSON, server_default=sa.text("'{}'::jsonb"), nullable=True
        ),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column(
            "updated_by",
            sa.Integer,
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=True,
        ),
    )
    op.create_index(
        "idx_platform_settings_updated_at", "platform_settings", ["updated_at"]
    )

    # ------------------------------------------------------------------
    # Trigger function: update_updated_at_column()
    # ------------------------------------------------------------------
    op.execute("""
        CREATE OR REPLACE FUNCTION update_updated_at_column()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = CURRENT_TIMESTAMP;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)

    # ------------------------------------------------------------------
    # Attach updated_at triggers to all tables that have the column
    # ------------------------------------------------------------------
    _tables_with_updated_at = [
        "organizations",
        "companies",
        "users",
        "employees",
        "customers",
        "customer_notes",
        "jobs",
        "platform_settings",
    ]
    for table in _tables_with_updated_at:
        trigger_name = f"update_{table}_updated_at"
        op.execute(f"DROP TRIGGER IF EXISTS {trigger_name} ON {table};")
        op.execute(f"""
            CREATE TRIGGER {trigger_name}
                BEFORE UPDATE ON {table}
                FOR EACH ROW
                EXECUTE FUNCTION update_updated_at_column();
        """)

    # ------------------------------------------------------------------
    # Utility function: cleanup expired auth tokens
    # ------------------------------------------------------------------
    op.execute("""
        CREATE OR REPLACE FUNCTION cleanup_expired_auth_tokens()
        RETURNS void AS $$
        BEGIN
            DELETE FROM refresh_tokens WHERE expires_at < CURRENT_TIMESTAMP;
            DELETE FROM token_blacklist WHERE expires_at < CURRENT_TIMESTAMP;
        END;
        $$ LANGUAGE plpgsql;
    """)

    # ------------------------------------------------------------------
    # Bootstrap data: superadmin user (required for the app to function)
    # Password: SuperAdmin123!
    # ------------------------------------------------------------------
    op.execute("""
        INSERT INTO users (
            email, hashed_password, first_name, last_name,
            role, is_active, owner_id, company_id, organization_id
        ) VALUES (
            'superadmin@system.local',
            '$2b$12$1eiIljOPjToirmKdjJPOZOIKS6MkU9i1uH/bstLn4PMSPqv2hLN6O',
            'System', 'Administrator',
            'superadmin', TRUE, NULL, NULL, NULL
        ) ON CONFLICT (email) DO NOTHING;
    """)

    # ------------------------------------------------------------------
    # Bootstrap data: default platform settings
    # ------------------------------------------------------------------
    op.execute("""
        INSERT INTO platform_settings (key, value, description) VALUES
            ('maintenance_mode', 'false', 'When true, only superadmins can access the platform'),
            ('max_login_attempts', '5', 'Maximum failed login attempts before account lockout'),
            ('default_billing_plan', '"free"', 'Default billing plan for new organizations'),
            ('platform_version', '"1.1.0"', 'Current platform version (superadmin reference)')
        ON CONFLICT (key) DO NOTHING;
    """)


def downgrade() -> None:
    # Drop tables in reverse dependency order
    op.drop_table("platform_settings")
    op.drop_table("audit_logs")
    op.drop_table("token_blacklist")
    op.drop_table("refresh_tokens")
    op.drop_table("job_history")
    op.drop_table("jobs")
    op.drop_table("customer_notes")
    op.drop_table("customers")
    op.drop_table("employees")
    op.drop_table("users")
    op.drop_table("companies")
    op.drop_table("organizations")

    # Drop functions
    op.execute("DROP FUNCTION IF EXISTS cleanup_expired_auth_tokens();")
    op.execute("DROP FUNCTION IF EXISTS update_updated_at_column() CASCADE;")
