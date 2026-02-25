-- CRM Calendar Database Initialization Script
-- Creates all tables for the microservices

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================
-- Organization Table (Platform-Level Entity)
-- ============================================

-- Organizations represent the top-level entity managed by superadmins.
-- Each tenant (company + owner) belongs to exactly one organization.
-- Superadmins can create, suspend, and manage organizations.
CREATE TABLE IF NOT EXISTS organizations (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    slug VARCHAR(100) UNIQUE NOT NULL,
    billing_email VARCHAR(255),
    billing_plan VARCHAR(50) DEFAULT 'free',
    max_users INTEGER DEFAULT 50,
    max_customers INTEGER DEFAULT 500,
    is_active BOOLEAN DEFAULT TRUE,
    suspended_at TIMESTAMP WITH TIME ZONE,
    suspended_reason TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT valid_billing_plan CHECK (billing_plan IN ('free', 'starter', 'professional', 'enterprise'))
);

CREATE INDEX IF NOT EXISTS idx_organizations_slug ON organizations(slug);
CREATE INDEX IF NOT EXISTS idx_organizations_is_active ON organizations(is_active);

-- ============================================
-- Company Table (Tenant Metadata)
-- ============================================

-- Companies table (represents a business / tenant)
CREATE TABLE IF NOT EXISTS companies (
    id SERIAL PRIMARY KEY,
    organization_id INTEGER REFERENCES organizations(id) ON DELETE SET NULL,
    name VARCHAR(255) NOT NULL,
    address TEXT,
    phone VARCHAR(50),
    email VARCHAR(255),
    eircode VARCHAR(10),
    logo_url VARCHAR(500),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- ============================================
-- User Service Tables
-- ============================================

-- Users table (business owners and their employees)
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    hashed_password VARCHAR(255) NOT NULL,
    first_name VARCHAR(255) NOT NULL,
    last_name VARCHAR(255) NOT NULL,
    phone VARCHAR(50),
    role VARCHAR(50) NOT NULL DEFAULT 'employee',
    is_active BOOLEAN DEFAULT TRUE,
    owner_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    company_id INTEGER REFERENCES companies(id) ON DELETE SET NULL,
    organization_id INTEGER REFERENCES organizations(id) ON DELETE SET NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    
    CONSTRAINT valid_role CHECK (role IN ('superadmin', 'owner', 'admin', 'manager', 'employee', 'viewer'))
);

-- Employees table (sub-users under business owners)
CREATE TABLE IF NOT EXISTS employees (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    owner_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    department VARCHAR(100),
    position VARCHAR(100),
    phone VARCHAR(50),
    hire_date DATE,
    hourly_rate DECIMAL(10, 2),
    skills TEXT,
    notes TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE(user_id, owner_id)
);

-- Index for faster lookups
CREATE INDEX IF NOT EXISTS idx_companies_name ON companies(name);
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_owner_id ON users(owner_id);
CREATE INDEX IF NOT EXISTS idx_users_company_id ON users(company_id);
CREATE INDEX IF NOT EXISTS idx_users_organization_id ON users(organization_id);
CREATE INDEX IF NOT EXISTS idx_employees_owner_id ON employees(owner_id);

-- ============================================
-- Customer Service Tables
-- ============================================

-- Customers table
CREATE TABLE IF NOT EXISTS customers (
    id SERIAL PRIMARY KEY,
    owner_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    email VARCHAR(255),
    phone VARCHAR(50),
    address TEXT,
    eircode VARCHAR(10),
    company_name VARCHAR(255),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Customer notes table
CREATE TABLE IF NOT EXISTS customer_notes (
    id SERIAL PRIMARY KEY,
    customer_id INTEGER NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    created_by_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    content TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for customer lookups
CREATE INDEX IF NOT EXISTS idx_customers_owner_id ON customers(owner_id);
CREATE INDEX IF NOT EXISTS idx_customers_email ON customers(email);
CREATE INDEX IF NOT EXISTS idx_customer_notes_customer_id ON customer_notes(customer_id);

-- ============================================
-- Job Service Tables
-- ============================================

-- Jobs table (calendar events/appointments)
CREATE TABLE IF NOT EXISTS jobs (
    id SERIAL PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    description TEXT,
    customer_id INTEGER REFERENCES customers(id) ON DELETE SET NULL,
    owner_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    assigned_employee_id INTEGER REFERENCES employees(id) ON DELETE SET NULL,
    created_by_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    status VARCHAR(50) NOT NULL DEFAULT 'pending',
    priority VARCHAR(50) NOT NULL DEFAULT 'normal',
    start_time TIMESTAMP WITH TIME ZONE,
    end_time TIMESTAMP WITH TIME ZONE,
    all_day BOOLEAN DEFAULT FALSE,
    location TEXT,
    eircode VARCHAR(10),
    estimated_duration INTEGER, -- in minutes
    actual_duration INTEGER, -- in minutes
    notes TEXT,
    color VARCHAR(20),
    is_recurring BOOLEAN DEFAULT FALSE,
    recurrence_rule VARCHAR(500),
    parent_job_id INTEGER REFERENCES jobs(id),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    
    CONSTRAINT valid_status CHECK (status IN ('pending', 'scheduled', 'in_progress', 'completed', 'cancelled', 'on_hold')),
    CONSTRAINT valid_priority CHECK (priority IN ('low', 'normal', 'high', 'urgent'))
);

-- Job history table (audit trail)
CREATE TABLE IF NOT EXISTS job_history (
    id SERIAL PRIMARY KEY,
    job_id INTEGER NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    changed_by_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    change_type VARCHAR(50),
    field_changed VARCHAR(100),
    old_value TEXT,
    new_value TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for job queries
CREATE INDEX IF NOT EXISTS idx_jobs_owner_id ON jobs(owner_id);
CREATE INDEX IF NOT EXISTS idx_jobs_customer_id ON jobs(customer_id);
CREATE INDEX IF NOT EXISTS idx_jobs_assigned_employee_id ON jobs(assigned_employee_id);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_start_time ON jobs(start_time);
CREATE INDEX IF NOT EXISTS idx_jobs_date_range ON jobs(start_time, end_time);
CREATE INDEX IF NOT EXISTS idx_job_history_job_id ON job_history(job_id);

-- ============================================
-- Auth Service Tables
-- ============================================

-- Refresh tokens table (for JWT refresh flow)
CREATE TABLE IF NOT EXISTS refresh_tokens (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    owner_id INTEGER NOT NULL,
    token_hash VARCHAR(64) NOT NULL UNIQUE,
    device_info VARCHAR(255),
    ip_address VARCHAR(45),
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    is_revoked BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Token blacklist table (for invalidated access tokens)
CREATE TABLE IF NOT EXISTS token_blacklist (
    id SERIAL PRIMARY KEY,
    jti VARCHAR(36) NOT NULL UNIQUE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for auth queries
CREATE INDEX IF NOT EXISTS idx_refresh_tokens_user_id ON refresh_tokens(user_id);
CREATE INDEX IF NOT EXISTS idx_refresh_tokens_token_hash ON refresh_tokens(token_hash);
CREATE INDEX IF NOT EXISTS idx_refresh_tokens_expires_at ON refresh_tokens(expires_at);
CREATE INDEX IF NOT EXISTS idx_token_blacklist_jti ON token_blacklist(jti);
CREATE INDEX IF NOT EXISTS idx_token_blacklist_expires_at ON token_blacklist(expires_at);

-- ============================================
-- Platform Administration Tables
-- ============================================

-- Audit logs table — records all significant platform actions.
-- Every superadmin action, impersonation, login, and sensitive
-- operation writes a row here for compliance and traceability.
CREATE TABLE IF NOT EXISTS audit_logs (
    id BIGSERIAL PRIMARY KEY,
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    actor_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    actor_email VARCHAR(255),
    actor_role VARCHAR(50),
    impersonator_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    organization_id INTEGER REFERENCES organizations(id) ON DELETE SET NULL,
    action VARCHAR(100) NOT NULL,
    resource_type VARCHAR(100),
    resource_id VARCHAR(100),
    details JSONB DEFAULT '{}',
    ip_address VARCHAR(45)
);

CREATE INDEX IF NOT EXISTS idx_audit_logs_timestamp ON audit_logs(timestamp);
CREATE INDEX IF NOT EXISTS idx_audit_logs_actor_id ON audit_logs(actor_id);
CREATE INDEX IF NOT EXISTS idx_audit_logs_organization_id ON audit_logs(organization_id);
CREATE INDEX IF NOT EXISTS idx_audit_logs_action ON audit_logs(action);
CREATE INDEX IF NOT EXISTS idx_audit_logs_resource ON audit_logs(resource_type, resource_id);

-- Platform settings table — key-value store for system-wide config.
-- Superadmins can read/write these via the admin API.
CREATE TABLE IF NOT EXISTS platform_settings (
    key VARCHAR(100) PRIMARY KEY,
    value JSONB NOT NULL DEFAULT '{}',
    description TEXT,
    updated_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_platform_settings_updated_at ON platform_settings(updated_at);

-- ============================================
-- Bootstrap Data (Required for Application)
-- ============================================
-- The superadmin is the platform bootstrap user.
-- All other users/orgs/companies are created via the API
-- (by integration tests or application workflows).

-- Insert superadmin user (password: "SuperAdmin123!")
-- Superadmins have NO owner_id (they are above the tenant level),
-- NO company_id, and NO organization_id (they manage ALL orgs).
INSERT INTO users (email, hashed_password, first_name, last_name, role, is_active, owner_id, company_id, organization_id)
VALUES (
    'superadmin@system.local',
    '$2b$12$1eiIljOPjToirmKdjJPOZOIKS6MkU9i1uH/bstLn4PMSPqv2hLN6O',
    'System',
    'Administrator',
    'superadmin',
    TRUE,
    NULL,
    NULL,
    NULL
) ON CONFLICT (email) DO NOTHING;

-- Grant function to update timestamps
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Create triggers for updated_at
DROP TRIGGER IF EXISTS update_companies_updated_at ON companies;
CREATE TRIGGER update_companies_updated_at
    BEFORE UPDATE ON companies
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_users_updated_at ON users;
CREATE TRIGGER update_users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_employees_updated_at ON employees;
CREATE TRIGGER update_employees_updated_at
    BEFORE UPDATE ON employees
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_customers_updated_at ON customers;
CREATE TRIGGER update_customers_updated_at
    BEFORE UPDATE ON customers
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_customer_notes_updated_at ON customer_notes;
CREATE TRIGGER update_customer_notes_updated_at
    BEFORE UPDATE ON customer_notes
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_jobs_updated_at ON jobs;
CREATE TRIGGER update_jobs_updated_at
    BEFORE UPDATE ON jobs
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Cleanup function for expired auth tokens (run periodically)
CREATE OR REPLACE FUNCTION cleanup_expired_auth_tokens()
RETURNS void AS $$
BEGIN
    DELETE FROM refresh_tokens WHERE expires_at < CURRENT_TIMESTAMP;
    DELETE FROM token_blacklist WHERE expires_at < CURRENT_TIMESTAMP;
END;
$$ LANGUAGE plpgsql;

-- Triggers for new tables
DROP TRIGGER IF EXISTS update_organizations_updated_at ON organizations;
CREATE TRIGGER update_organizations_updated_at
    BEFORE UPDATE ON organizations
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_platform_settings_updated_at ON platform_settings;
CREATE TRIGGER update_platform_settings_updated_at
    BEFORE UPDATE ON platform_settings
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Seed default platform settings
INSERT INTO platform_settings (key, value, description)
VALUES
    ('maintenance_mode', 'false', 'When true, only superadmins can access the platform'),
    ('max_login_attempts', '5', 'Maximum failed login attempts before account lockout'),
    ('default_billing_plan', '"free"', 'Default billing plan for new organizations'),
    ('platform_version', '"1.1.0"', 'Current platform version (superadmin reference)')
ON CONFLICT (key) DO NOTHING;

-- Output success message
DO $$
BEGIN
    RAISE NOTICE 'CRM Calendar database initialized successfully!';
END $$;
