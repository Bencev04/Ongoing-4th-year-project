-- ============================================
-- CRM Calendar — Demo Seed Data (Local Development)
-- ============================================
-- This file is loaded AFTER init-db.sql (schema + superadmin).
-- It provides sample organizations, companies, and users for
-- local development and manual testing.
--
-- NOT used by integration tests — they create their own data
-- via API calls (see tests/integration/conftest.py).
-- ============================================

-- Default organization
INSERT INTO organizations (name, slug, billing_email, billing_plan, max_users, max_customers)
VALUES (
    'Default Organization',
    'default-org',
    'billing@demoservices.ie',
    'professional',
    50,
    500
) ON CONFLICT (slug) DO NOTHING;

-- Demo company
INSERT INTO companies (organization_id, name, address, phone, email, eircode, is_active)
SELECT
    o.id,
    'Demo Services Ltd.',
    '456 Business Park, Dublin',
    '+353 1 555 0100',
    'info@demoservices.ie',
    'D04 AB12',
    TRUE
FROM organizations o WHERE o.slug = 'default-org'
ON CONFLICT DO NOTHING;

-- Demo owner user (password: "password123")
INSERT INTO users (email, hashed_password, first_name, last_name, role, is_active, company_id, organization_id)
SELECT
    'owner@demo.com',
    '$2b$12$HyJZyi8NViS4R.tlKYvaqO/IfnFY3Iy7B41z7oy4doo9bpTXZVQJm',
    'Demo',
    'Owner',
    'owner',
    TRUE,
    c.id,
    c.organization_id
FROM companies c WHERE c.name = 'Demo Services Ltd.'
ON CONFLICT (email) DO NOTHING;

UPDATE users SET owner_id = id WHERE email = 'owner@demo.com' AND owner_id IS NULL;

-- Demo employee user (password: "password123")
INSERT INTO users (email, hashed_password, first_name, last_name, role, owner_id, is_active, company_id, organization_id)
SELECT
    'employee@demo.com',
    '$2b$12$HyJZyi8NViS4R.tlKYvaqO/IfnFY3Iy7B41z7oy4doo9bpTXZVQJm',
    'Demo',
    'Employee',
    'employee',
    o.id,
    TRUE,
    o.company_id,
    o.organization_id
FROM users o WHERE o.email = 'owner@demo.com'
ON CONFLICT (email) DO NOTHING;

-- Demo admin user (password: "password123")
INSERT INTO users (email, hashed_password, first_name, last_name, role, owner_id, is_active, company_id, organization_id)
SELECT
    'admin@demo.com',
    '$2b$12$HyJZyi8NViS4R.tlKYvaqO/IfnFY3Iy7B41z7oy4doo9bpTXZVQJm',
    'Demo',
    'Admin',
    'admin',
    o.id,
    TRUE,
    o.company_id,
    o.organization_id
FROM users o WHERE o.email = 'owner@demo.com'
ON CONFLICT (email) DO NOTHING;

-- Demo manager user (password: "password123")
INSERT INTO users (email, hashed_password, first_name, last_name, role, owner_id, is_active, company_id, organization_id)
SELECT
    'manager@demo.com',
    '$2b$12$HyJZyi8NViS4R.tlKYvaqO/IfnFY3Iy7B41z7oy4doo9bpTXZVQJm',
    'Demo',
    'Manager',
    'manager',
    o.id,
    TRUE,
    o.company_id,
    o.organization_id
FROM users o WHERE o.email = 'owner@demo.com'
ON CONFLICT (email) DO NOTHING;

-- Demo viewer user (password: "password123")
INSERT INTO users (email, hashed_password, first_name, last_name, role, owner_id, is_active, company_id, organization_id)
SELECT
    'viewer@demo.com',
    '$2b$12$HyJZyi8NViS4R.tlKYvaqO/IfnFY3Iy7B41z7oy4doo9bpTXZVQJm',
    'Demo',
    'Viewer',
    'viewer',
    o.id,
    TRUE,
    o.company_id,
    o.organization_id
FROM users o WHERE o.email = 'owner@demo.com'
ON CONFLICT (email) DO NOTHING;

-- ============================================
-- Second Tenant (cross-tenant demo data)
-- ============================================

INSERT INTO organizations (name, slug, billing_email, billing_plan, max_users, max_customers)
VALUES (
    'Second Organization',
    'second-org',
    'billing@secondorg.ie',
    'starter',
    10,
    100
) ON CONFLICT (slug) DO NOTHING;

INSERT INTO companies (organization_id, name, address, phone, email, eircode, is_active)
SELECT
    o.id,
    'Second Corp.',
    '789 Other Road, Cork',
    '+353 21 555 0200',
    'info@secondcorp.ie',
    'T12 CD34',
    TRUE
FROM organizations o WHERE o.slug = 'second-org'
ON CONFLICT DO NOTHING;

INSERT INTO users (email, hashed_password, first_name, last_name, role, is_active, company_id, organization_id)
SELECT
    'owner2@demo.com',
    '$2b$12$HyJZyi8NViS4R.tlKYvaqO/IfnFY3Iy7B41z7oy4doo9bpTXZVQJm',
    'Second',
    'Owner',
    'owner',
    TRUE,
    c.id,
    c.organization_id
FROM companies c WHERE c.name = 'Second Corp.'
ON CONFLICT (email) DO NOTHING;

UPDATE users SET owner_id = id WHERE email = 'owner2@demo.com' AND owner_id IS NULL;

-- ============================================
-- Demo Employee, Customer & Job Records
-- ============================================

INSERT INTO employees (user_id, owner_id, department, position, phone, hire_date, hourly_rate, skills, notes, is_active)
SELECT
    e.id, o.id,
    'Operations', 'Field Technician', '+353 85 123 4567',
    CURRENT_DATE - INTERVAL '6 months', 35.50,
    'Electrical, Plumbing, Carpentry',
    'Experienced field technician with 5 years of experience', TRUE
FROM users e, users o
WHERE e.email = 'employee@demo.com' AND o.email = 'owner@demo.com'
ON CONFLICT DO NOTHING;

INSERT INTO customers (owner_id, name, email, phone, address, eircode, company_name, is_active)
SELECT id, 'John Smith', 'john.smith@example.com', '+353 1 987 6543',
    '123 Main Street, Dublin', 'D02 XY45', 'Smith & Co.', TRUE
FROM users WHERE email = 'owner@demo.com'
ON CONFLICT DO NOTHING;

INSERT INTO jobs (title, description, customer_id, owner_id, created_by_id, status, priority, start_time, end_time, location, eircode, estimated_duration)
SELECT
    'Kitchen Renovation Consultation',
    'Initial consultation for kitchen renovation project',
    c.id, u.id, u.id, 'scheduled', 'normal',
    CURRENT_TIMESTAMP + INTERVAL '2 days',
    CURRENT_TIMESTAMP + INTERVAL '2 days' + INTERVAL '2 hours',
    '123 Main Street, Dublin', 'D02 XY45', 120
FROM users u, customers c
WHERE u.email = 'owner@demo.com' AND c.email = 'john.smith@example.com'
ON CONFLICT DO NOTHING;

INSERT INTO jobs (title, description, owner_id, created_by_id, status, priority, location, estimated_duration)
SELECT 'Follow-up Call', 'Schedule follow-up with potential client',
    id, id, 'pending', 'high', NULL, 30
FROM users WHERE email = 'owner@demo.com'
ON CONFLICT DO NOTHING;

DO $$ BEGIN RAISE NOTICE 'Demo seed data loaded successfully!'; END $$;
