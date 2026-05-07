-- ============================================
-- CRM Calendar - Demo Seed Data (Local Development)
-- ============================================
-- This file is loaded AFTER Alembic migrations (schema + superadmin).
-- It provides sample organizations, companies, and users for
-- local development and manual testing.
--
-- NOT used by integration tests - they create their own data
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
AND NOT EXISTS (SELECT 1 FROM companies WHERE name = 'Demo Services Ltd.' AND organization_id = o.id);

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

-- Additional employee users for calendar demo variety (password: "password123")
INSERT INTO users (email, hashed_password, first_name, last_name, role, owner_id, is_active, company_id, organization_id)
SELECT
    'employee2@demo.com',
    '$2b$12$HyJZyi8NViS4R.tlKYvaqO/IfnFY3Iy7B41z7oy4doo9bpTXZVQJm',
    'Ciara',
    'Walsh',
    'employee',
    o.id,
    TRUE,
    o.company_id,
    o.organization_id
FROM users o WHERE o.email = 'owner@demo.com'
ON CONFLICT (email) DO NOTHING;

INSERT INTO users (email, hashed_password, first_name, last_name, role, owner_id, is_active, company_id, organization_id)
SELECT
    'employee3@demo.com',
    '$2b$12$HyJZyi8NViS4R.tlKYvaqO/IfnFY3Iy7B41z7oy4doo9bpTXZVQJm',
    'Liam',
    'Murphy',
    'employee',
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
AND NOT EXISTS (SELECT 1 FROM companies WHERE name = 'Second Corp.' AND organization_id = o.id);

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
-- Demo Employee Records
-- ============================================
-- Employee records link users to the employee table so they
-- appear in the "Assign Employee" dropdown on the calendar.

-- Employee #1 - field technician (employee@demo.com)
INSERT INTO employees (user_id, owner_id, department, position, phone, hire_date, hourly_rate, skills, notes, is_active)
SELECT
    e.id, o.id,
    'Operations', 'Field Technician', '+353 85 123 4567',
    '2025-09-01'::date, 35.50,
    'Electrical, Plumbing, Carpentry',
    'Experienced field technician with 5 years of experience', TRUE
FROM users e, users o
WHERE e.email = 'employee@demo.com' AND o.email = 'owner@demo.com'
ON CONFLICT DO NOTHING;

-- Employee #2 - project manager (manager@demo.com)
INSERT INTO employees (user_id, owner_id, department, position, phone, hire_date, hourly_rate, skills, notes, is_active)
SELECT
    m.id, o.id,
    'Management', 'Project Manager', '+353 85 234 5678',
    '2025-06-15'::date, 45.00,
    'Scheduling, Client Relations, Budgeting',
    'Oversees large-scale renovation projects', TRUE
FROM users m, users o
WHERE m.email = 'manager@demo.com' AND o.email = 'owner@demo.com'
ON CONFLICT DO NOTHING;

-- Employee #3 - admin assistant (admin@demo.com)
INSERT INTO employees (user_id, owner_id, department, position, phone, hire_date, hourly_rate, skills, notes, is_active)
SELECT
    a.id, o.id,
    'Administration', 'Office Administrator', '+353 85 345 6789',
    '2025-03-01'::date, 28.00,
    'Invoicing, Customer Support, Scheduling',
    'Handles office administration and customer queries', TRUE
FROM users a, users o
WHERE a.email = 'admin@demo.com' AND o.email = 'owner@demo.com'
ON CONFLICT DO NOTHING;

-- Employee #4 - senior electrician (employee2@demo.com)
INSERT INTO employees (user_id, owner_id, department, position, phone, hire_date, hourly_rate, skills, notes, is_active)
SELECT
    e.id, o.id,
    'Operations', 'Senior Electrician', '+353 85 456 7890',
    '2024-11-01'::date, 42.00,
    'Industrial Wiring, EV Chargers, Solar PV, RECI Certified',
    'Fully qualified senior electrician, 10 years experience', TRUE
FROM users e, users o
WHERE e.email = 'employee2@demo.com' AND o.email = 'owner@demo.com'
ON CONFLICT DO NOTHING;

-- Employee #5 - apprentice technician (employee3@demo.com)
INSERT INTO employees (user_id, owner_id, department, position, phone, hire_date, hourly_rate, skills, notes, is_active)
SELECT
    e.id, o.id,
    'Operations', 'Apprentice Technician', '+353 85 567 8901',
    '2025-12-01'::date, 16.50,
    'Basic Wiring, PAT Testing, Cable Management',
    'Third-year electrical apprentice, shadows senior staff', TRUE
FROM users e, users o
WHERE e.email = 'employee3@demo.com' AND o.email = 'owner@demo.com'
ON CONFLICT DO NOTHING;

-- ============================================
-- Demo Customer Records
-- ============================================

-- Clear existing demo customers to prevent duplicates on re-seed.
-- Must delete referencing records first (FK constraints).
DELETE FROM customer_notes WHERE customer_id IN (
    SELECT id FROM customers WHERE owner_id = (SELECT id FROM users WHERE email = 'owner@demo.com')
);
DELETE FROM customers WHERE owner_id = (SELECT id FROM users WHERE email = 'owner@demo.com');

-- Customer #1
INSERT INTO customers (owner_id, name, email, phone, address, eircode, company_name, is_active)
SELECT id, 'John Smith', 'john.smith@example.com', '+353 1 987 6543',
    '123 Main Street, Dublin 2', 'D02 XY45', 'Smith & Co.', TRUE
FROM users WHERE email = 'owner@demo.com';

-- Customer #2
INSERT INTO customers (owner_id, name, email, phone, address, eircode, company_name, is_active)
SELECT id, 'Sarah O''Brien', 'sarah.obrien@example.com', '+353 1 456 7890',
    '45 Grafton Street, Dublin 2', 'D02 VF25', 'O''Brien Interiors', TRUE
FROM users WHERE email = 'owner@demo.com';

-- Customer #3
INSERT INTO customers (owner_id, name, email, phone, address, eircode, company_name, is_active)
SELECT id, 'Michael Byrne', 'michael.byrne@example.com', '+353 21 333 4455',
    '8 Patrick Street, Cork', 'T12 W8KP', 'Byrne Construction', TRUE
FROM users WHERE email = 'owner@demo.com';

-- Customer #4
INSERT INTO customers (owner_id, name, email, phone, address, eircode, company_name, is_active)
SELECT id, 'Emma Kelly', 'emma.kelly@example.com', '+353 61 222 3344',
    '12 O''Connell Street, Limerick', 'V94 T28R', NULL, TRUE
FROM users WHERE email = 'owner@demo.com';

-- Customer #5
INSERT INTO customers (owner_id, name, email, phone, address, eircode, company_name, is_active)
SELECT id, 'Tom Murphy', 'tom.murphy@example.com', '+353 91 444 5566',
    '67 Eyre Square, Galway', 'H91 KT23', 'Murphy Property Management', TRUE
FROM users WHERE email = 'owner@demo.com';

-- Customer #6
INSERT INTO customers (owner_id, name, email, phone, address, eircode, company_name, is_active)
SELECT id, 'Aoife Doyle', 'aoife.doyle@example.com', '+353 51 333 7788',
    '33 The Quay, Waterford', 'X91 PK12', 'Doyle Enterprises', TRUE
FROM users WHERE email = 'owner@demo.com';

-- ============================================
-- Demo Job Records - 2026 Calendar Data
-- ============================================
-- Jobs are seeded with hard-coded 2026 dates to populate
-- the calendar with realistic, varied entries:
--   • Multi-day jobs (spanning 2+ days)
--   • Three jobs on the same day
--   • Mix of statuses and priorities
--   • Different employees and customers assigned

-- Clear existing demo jobs to prevent duplicates on re-seed.
-- Must delete child records first (FK constraints).
DELETE FROM job_employees WHERE job_id IN (
    SELECT id FROM jobs WHERE owner_id = (SELECT id FROM users WHERE email = 'owner@demo.com')
);
DELETE FROM job_history WHERE job_id IN (
    SELECT id FROM jobs WHERE owner_id = (SELECT id FROM users WHERE email = 'owner@demo.com')
);
UPDATE jobs SET parent_job_id = NULL WHERE owner_id = (SELECT id FROM users WHERE email = 'owner@demo.com') AND parent_job_id IS NOT NULL;
DELETE FROM jobs WHERE owner_id = (SELECT id FROM users WHERE email = 'owner@demo.com');

-- ──────────────────────────────────────────
-- Week of 12 Jan 2026 - triple-booked Monday
-- ──────────────────────────────────────────

-- Job 1: Mon 12 Jan - morning (assigned to employee@demo.com)
INSERT INTO jobs (title, description, customer_id, owner_id, created_by_id,
                  status, priority, start_time, end_time, location, eircode, estimated_duration, color)
SELECT
    'Kitchen Renovation Consultation',
    'Initial site visit and measurements for kitchen renovation project. Discuss layout options and budget.',
    c.id, o.id, o.id,
    'scheduled', 'high',
    '2026-01-12 09:00:00+00'::timestamptz,
    '2026-01-12 11:00:00+00'::timestamptz,
    '123 Main Street, Dublin 2', 'D02 XY45', 120, '#3B82F6'
FROM users o
JOIN customers c ON c.owner_id = o.id AND c.email = 'john.smith@example.com'
WHERE o.email = 'owner@demo.com'
ON CONFLICT DO NOTHING;

-- Job 2: Mon 12 Jan - midday (assigned to manager@demo.com)
INSERT INTO jobs (title, description, customer_id, owner_id, created_by_id,
                  status, priority, start_time, end_time, location, eircode, estimated_duration, color)
SELECT
    'Bathroom Plumbing Repair',
    'Fix leaking shower valve and replace corroded pipes under bathroom sink.',
    c.id, o.id, o.id,
    'scheduled', 'urgent',
    '2026-01-12 12:00:00+00'::timestamptz,
    '2026-01-12 14:30:00+00'::timestamptz,
    '45 Grafton Street, Dublin 2', 'D02 VF25', 150, '#EF4444'
FROM users o
JOIN customers c ON c.owner_id = o.id AND c.email = 'sarah.obrien@example.com'
WHERE o.email = 'owner@demo.com'
ON CONFLICT DO NOTHING;

-- Job 3: Mon 12 Jan - afternoon (assigned to admin@demo.com)
INSERT INTO jobs (title, description, customer_id, owner_id, created_by_id,
                  status, priority, start_time, end_time, location, eircode, estimated_duration, color)
SELECT
    'Office Wiring Inspection',
    'Annual safety inspection of office electrical wiring and fuse board.',
    c.id, o.id, o.id,
    'scheduled', 'normal',
    '2026-01-12 15:00:00+00'::timestamptz,
    '2026-01-12 17:00:00+00'::timestamptz,
    '8 Patrick Street, Cork', 'T12 W8KP', 120, '#F59E0B'
FROM users o
JOIN customers c ON c.owner_id = o.id AND c.email = 'michael.byrne@example.com'
WHERE o.email = 'owner@demo.com'
ON CONFLICT DO NOTHING;

-- ──────────────────────────────────────────
-- Multi-day job: Wed 14 – Fri 16 Jan 2026
-- ──────────────────────────────────────────

INSERT INTO jobs (title, description, customer_id, owner_id, created_by_id,
                  status, priority, start_time, end_time, location, eircode, estimated_duration, color)
SELECT
    'Full House Rewiring - Phase 1',
    'Complete rewiring of a 4-bed detached house. Phase 1 covers ground floor and kitchen circuits.',
    c.id, o.id, o.id,
    'scheduled', 'high',
    '2026-01-14 08:00:00+00'::timestamptz,
    '2026-01-16 17:00:00+00'::timestamptz,
    '12 O''Connell Street, Limerick', 'V94 T28R', 1440, '#8B5CF6'
FROM users o
JOIN customers c ON c.owner_id = o.id AND c.email = 'emma.kelly@example.com'
WHERE o.email = 'owner@demo.com'
ON CONFLICT DO NOTHING;

-- ──────────────────────────────────────────
-- Week of 19 Jan - completed and in-progress jobs
-- ──────────────────────────────────────────

INSERT INTO jobs (title, description, customer_id, owner_id, created_by_id,
                  status, priority, start_time, end_time, location, eircode, estimated_duration)
SELECT
    'Boiler Service',
    'Annual boiler service and carbon monoxide check.',
    c.id, o.id, o.id,
    'completed', 'normal',
    '2026-01-19 10:00:00+00'::timestamptz,
    '2026-01-19 11:30:00+00'::timestamptz,
    '123 Main Street, Dublin 2', 'D02 XY45', 90
FROM users o
JOIN customers c ON c.owner_id = o.id AND c.email = 'john.smith@example.com'
WHERE o.email = 'owner@demo.com'
ON CONFLICT DO NOTHING;

INSERT INTO jobs (title, description, customer_id, owner_id, created_by_id,
                  status, priority, start_time, end_time, location, estimated_duration)
SELECT
    'Garden Lighting Installation',
    'Install 8 low-voltage LED lights along driveway and patio area.',
    c.id, o.id, o.id,
    'in_progress', 'normal',
    '2026-01-20 09:00:00+00'::timestamptz,
    '2026-01-20 16:00:00+00'::timestamptz,
    '45 Grafton Street, Dublin 2', 420
FROM users o
JOIN customers c ON c.owner_id = o.id AND c.email = 'sarah.obrien@example.com'
WHERE o.email = 'owner@demo.com'
ON CONFLICT DO NOTHING;

-- ──────────────────────────────────────────
-- Late Jan - cancelled and on-hold jobs
-- ──────────────────────────────────────────

INSERT INTO jobs (title, description, customer_id, owner_id, created_by_id,
                  status, priority, start_time, end_time, location, eircode, estimated_duration)
SELECT
    'Attic Conversion Survey',
    'Structural survey for attic conversion. Cancelled by customer.',
    c.id, o.id, o.id,
    'cancelled', 'low',
    '2026-01-22 14:00:00+00'::timestamptz,
    '2026-01-22 16:00:00+00'::timestamptz,
    '8 Patrick Street, Cork', 'T12 W8KP', 120
FROM users o
JOIN customers c ON c.owner_id = o.id AND c.email = 'michael.byrne@example.com'
WHERE o.email = 'owner@demo.com'
ON CONFLICT DO NOTHING;

INSERT INTO jobs (title, description, customer_id, owner_id, created_by_id,
                  status, priority, start_time, end_time, location, estimated_duration, color)
SELECT
    'Underfloor Heating Consultation',
    'On hold - waiting for architect drawings before proceeding.',
    c.id, o.id, o.id,
    'on_hold', 'normal',
    '2026-01-26 10:00:00+00'::timestamptz,
    '2026-01-26 12:00:00+00'::timestamptz,
    '12 O''Connell Street, Limerick', 120, '#6B7280'
FROM users o
JOIN customers c ON c.owner_id = o.id AND c.email = 'emma.kelly@example.com'
WHERE o.email = 'owner@demo.com'
ON CONFLICT DO NOTHING;

-- ──────────────────────────────────────────
-- February 2026 - spread across the month
-- ──────────────────────────────────────────

INSERT INTO jobs (title, description, customer_id, owner_id, created_by_id,
                  status, priority, start_time, end_time, location, eircode, estimated_duration, color)
SELECT
    'Emergency Pipe Burst Repair',
    'Emergency callout - frozen pipe burst in utility room. Water damage containment required.',
    c.id, o.id, o.id,
    'completed', 'urgent',
    '2026-02-02 07:30:00+00'::timestamptz,
    '2026-02-02 12:00:00+00'::timestamptz,
    '123 Main Street, Dublin 2', 'D02 XY45', 270, '#DC2626'
FROM users o
JOIN customers c ON c.owner_id = o.id AND c.email = 'john.smith@example.com'
WHERE o.email = 'owner@demo.com'
ON CONFLICT DO NOTHING;

-- Multi-day: Mon 9 – Wed 11 Feb
INSERT INTO jobs (title, description, customer_id, owner_id, created_by_id,
                  status, priority, start_time, end_time, location, eircode, estimated_duration, color)
SELECT
    'Shop Fit-Out - Electrical',
    'Complete electrical fit-out for new retail unit. Lighting, sockets, and alarm system wiring.',
    c.id, o.id, o.id,
    'scheduled', 'high',
    '2026-02-09 08:00:00+00'::timestamptz,
    '2026-02-11 17:00:00+00'::timestamptz,
    '8 Patrick Street, Cork', 'T12 W8KP', 1500, '#8B5CF6'
FROM users o
JOIN customers c ON c.owner_id = o.id AND c.email = 'michael.byrne@example.com'
WHERE o.email = 'owner@demo.com'
ON CONFLICT DO NOTHING;

INSERT INTO jobs (title, description, customer_id, owner_id, created_by_id,
                  status, priority, start_time, end_time, location, estimated_duration)
SELECT
    'Smart Home Setup',
    'Install smart thermostat, doorbell camera, and 4 smart light switches.',
    c.id, o.id, o.id,
    'scheduled', 'normal',
    '2026-02-16 10:00:00+00'::timestamptz,
    '2026-02-16 15:00:00+00'::timestamptz,
    '45 Grafton Street, Dublin 2', 300
FROM users o
JOIN customers c ON c.owner_id = o.id AND c.email = 'sarah.obrien@example.com'
WHERE o.email = 'owner@demo.com'
ON CONFLICT DO NOTHING;

INSERT INTO jobs (title, description, customer_id, owner_id, created_by_id,
                  status, priority, start_time, end_time, location, eircode, estimated_duration)
SELECT
    'EV Charger Installation Quote',
    'Site survey and quote for home EV charger. Check consumer unit capacity.',
    c.id, o.id, o.id,
    'scheduled', 'low',
    '2026-02-20 11:00:00+00'::timestamptz,
    '2026-02-20 12:00:00+00'::timestamptz,
    '12 O''Connell Street, Limerick', 'V94 T28R', 60
FROM users o
JOIN customers c ON c.owner_id = o.id AND c.email = 'emma.kelly@example.com'
WHERE o.email = 'owner@demo.com'
ON CONFLICT DO NOTHING;

-- ──────────────────────────────────────────
-- March 2026 - triple-booked day + multi-day
-- ──────────────────────────────────────────

-- Triple-booked Wed 4 Mar
INSERT INTO jobs (title, description, customer_id, owner_id, created_by_id,
                  status, priority, start_time, end_time, location, eircode, estimated_duration, color)
SELECT
    'Fire Alarm Certification',
    'Annual fire alarm test and certification for commercial premises.',
    c.id, o.id, o.id,
    'scheduled', 'high',
    '2026-03-04 08:30:00+00'::timestamptz,
    '2026-03-04 10:30:00+00'::timestamptz,
    '8 Patrick Street, Cork', 'T12 W8KP', 120, '#F59E0B'
FROM users o
JOIN customers c ON c.owner_id = o.id AND c.email = 'michael.byrne@example.com'
WHERE o.email = 'owner@demo.com'
ON CONFLICT DO NOTHING;

INSERT INTO jobs (title, description, customer_id, owner_id, created_by_id,
                  status, priority, start_time, end_time, location, eircode, estimated_duration)
SELECT
    'Security Camera Installation',
    'Install 4 outdoor IP cameras and configure NVR system.',
    c.id, o.id, o.id,
    'scheduled', 'normal',
    '2026-03-04 11:00:00+00'::timestamptz,
    '2026-03-04 15:00:00+00'::timestamptz,
    '123 Main Street, Dublin 2', 'D02 XY45', 240
FROM users o
JOIN customers c ON c.owner_id = o.id AND c.email = 'john.smith@example.com'
WHERE o.email = 'owner@demo.com'
ON CONFLICT DO NOTHING;

INSERT INTO jobs (title, description, customer_id, owner_id, created_by_id,
                  status, priority, start_time, end_time, location, estimated_duration, color)
SELECT
    'Outdoor Socket Installation',
    'Install 2 weatherproof outdoor sockets in rear garden.',
    c.id, o.id, o.id,
    'scheduled', 'low',
    '2026-03-04 15:30:00+00'::timestamptz,
    '2026-03-04 17:00:00+00'::timestamptz,
    '45 Grafton Street, Dublin 2', 90, '#10B981'
FROM users o
JOIN customers c ON c.owner_id = o.id AND c.email = 'sarah.obrien@example.com'
WHERE o.email = 'owner@demo.com'
ON CONFLICT DO NOTHING;

-- Multi-day: Mon 16 – Thu 19 Mar
INSERT INTO jobs (title, description, customer_id, owner_id, created_by_id,
                  status, priority, start_time, end_time, location, eircode, estimated_duration, color)
SELECT
    'Full House Rewiring - Phase 2',
    'Phase 2: First floor and attic circuits. Includes new consumer unit and RECI cert.',
    c.id, o.id, o.id,
    'scheduled', 'high',
    '2026-03-16 08:00:00+00'::timestamptz,
    '2026-03-19 17:00:00+00'::timestamptz,
    '12 O''Connell Street, Limerick', 'V94 T28R', 1920, '#8B5CF6'
FROM users o
JOIN customers c ON c.owner_id = o.id AND c.email = 'emma.kelly@example.com'
WHERE o.email = 'owner@demo.com'
ON CONFLICT DO NOTHING;

-- ──────────────────────────────────────────
-- March 2026 - Full calendar demo (~50 jobs)
-- Covers every weekday + some weekends,
-- all statuses, priorities, employees, and customers
-- ──────────────────────────────────────────

-- ── Week 1: Mar 1–7 ──

-- Mar 1 (Sun): Weekend emergency callout
INSERT INTO jobs (title, description, customer_id, owner_id, created_by_id,
                  status, priority, start_time, end_time, location, eircode, estimated_duration, color)
SELECT
    'Emergency Boiler Breakdown',
    'Weekend callout - boiler stopped producing hot water. Diagnosed faulty diverter valve.',
    c.id, o.id, o.id,
    'completed', 'urgent',
    '2026-03-01 10:00:00+00'::timestamptz,
    '2026-03-01 13:00:00+00'::timestamptz,
    '123 Main Street, Dublin 2', 'D02 XY45', 180, '#DC2626'
FROM users o
JOIN customers c ON c.owner_id = o.id AND c.email = 'john.smith@example.com'
WHERE o.email = 'owner@demo.com'
ON CONFLICT DO NOTHING;

-- Mar 2 (Mon): Three different employees, three different customers
INSERT INTO jobs (title, description, customer_id, owner_id, created_by_id,
                  status, priority, start_time, end_time, location, eircode, estimated_duration, color)
SELECT
    'Smoke Detector Battery Replacement',
    'Replace batteries and test all smoke detectors across 6-unit apartment building.',
    c.id, o.id, o.id,
    'completed', 'low',
    '2026-03-02 09:00:00+00'::timestamptz,
    '2026-03-02 10:30:00+00'::timestamptz,
    '67 Eyre Square, Galway', 'H91 KT23', 90, '#10B981'
FROM users o
JOIN customers c ON c.owner_id = o.id AND c.email = 'tom.murphy@example.com'
WHERE o.email = 'owner@demo.com'
ON CONFLICT DO NOTHING;

INSERT INTO jobs (title, description, customer_id, owner_id, created_by_id,
                  status, priority, start_time, end_time, location, eircode, estimated_duration)
SELECT
    'Dishwasher Electrical Connection',
    'Run dedicated 20A circuit from consumer unit for new integrated dishwasher.',
    c.id, o.id, o.id,
    'completed', 'normal',
    '2026-03-02 11:00:00+00'::timestamptz,
    '2026-03-02 13:00:00+00'::timestamptz,
    '45 Grafton Street, Dublin 2', 'D02 VF25', 120
FROM users o
JOIN customers c ON c.owner_id = o.id AND c.email = 'sarah.obrien@example.com'
WHERE o.email = 'owner@demo.com'
ON CONFLICT DO NOTHING;

INSERT INTO jobs (title, description, customer_id, owner_id, created_by_id,
                  status, priority, start_time, end_time, location, eircode, estimated_duration, color)
SELECT
    'Heat Pump Annual Service',
    'Annual inspection and performance test of air-source heat pump system.',
    c.id, o.id, o.id,
    'completed', 'normal',
    '2026-03-02 14:00:00+00'::timestamptz,
    '2026-03-02 16:30:00+00'::timestamptz,
    '33 The Quay, Waterford', 'X91 PK12', 150, '#3B82F6'
FROM users o
JOIN customers c ON c.owner_id = o.id AND c.email = 'aoife.doyle@example.com'
WHERE o.email = 'owner@demo.com'
ON CONFLICT DO NOTHING;

-- Mar 3 (Tue): Same employee doing two jobs in one day + another employee
INSERT INTO jobs (title, description, customer_id, owner_id, created_by_id,
                  status, priority, start_time, end_time, location, eircode, estimated_duration, color)
SELECT
    'Commercial Kitchen Extractor Wiring',
    'Replace wiring for industrial extractor hood. Isolate, rewire, and test three-phase motor.',
    c.id, o.id, o.id,
    'completed', 'high',
    '2026-03-03 08:00:00+00'::timestamptz,
    '2026-03-03 12:00:00+00'::timestamptz,
    '8 Patrick Street, Cork', 'T12 W8KP', 240, '#F59E0B'
FROM users o
JOIN customers c ON c.owner_id = o.id AND c.email = 'michael.byrne@example.com'
WHERE o.email = 'owner@demo.com'
ON CONFLICT DO NOTHING;

INSERT INTO jobs (title, description, customer_id, owner_id, created_by_id,
                  status, priority, start_time, end_time, location, eircode, estimated_duration, color)
SELECT
    'Data Cabling - Small Office',
    'Install Cat6a cabling for 12 desk points and 2 server rack connections.',
    c.id, o.id, o.id,
    'completed', 'normal',
    '2026-03-03 09:00:00+00'::timestamptz,
    '2026-03-03 13:00:00+00'::timestamptz,
    '33 The Quay, Waterford', 'X91 PK12', 240, '#3B82F6'
FROM users o
JOIN customers c ON c.owner_id = o.id AND c.email = 'aoife.doyle@example.com'
WHERE o.email = 'owner@demo.com'
ON CONFLICT DO NOTHING;

INSERT INTO jobs (title, description, customer_id, owner_id, created_by_id,
                  status, priority, start_time, end_time, location, eircode, estimated_duration)
SELECT
    'Immersion Heater Replacement',
    'Remove faulty immersion element and thermostat. Fit new 3kW element and test.',
    c.id, o.id, o.id,
    'completed', 'normal',
    '2026-03-03 14:00:00+00'::timestamptz,
    '2026-03-03 16:00:00+00'::timestamptz,
    '12 O''Connell Street, Limerick', 'V94 T28R', 120
FROM users o
JOIN customers c ON c.owner_id = o.id AND c.email = 'emma.kelly@example.com'
WHERE o.email = 'owner@demo.com'
ON CONFLICT DO NOTHING;

-- Mar 4 (Wed): Already has 3 jobs - add 2 more (5 total, busiest day)
INSERT INTO jobs (title, description, customer_id, owner_id, created_by_id,
                  status, priority, start_time, end_time, location, eircode, estimated_duration, color)
SELECT
    'Parking Lot Floodlight Repair',
    'Two of eight parking lot floodlights failed. Replace LED drivers and re-aim units.',
    c.id, o.id, o.id,
    'scheduled', 'low',
    '2026-03-04 11:00:00+00'::timestamptz,
    '2026-03-04 13:30:00+00'::timestamptz,
    '67 Eyre Square, Galway', 'H91 KT23', 150, '#10B981'
FROM users o
JOIN customers c ON c.owner_id = o.id AND c.email = 'tom.murphy@example.com'
WHERE o.email = 'owner@demo.com'
ON CONFLICT DO NOTHING;

INSERT INTO jobs (title, description, customer_id, owner_id, created_by_id,
                  status, priority, start_time, end_time, location, eircode, estimated_duration)
SELECT
    'Apprentice Shadowing - Fire Alarm Cert',
    'Apprentice shadows senior tech during fire alarm certification at commercial premises.',
    c.id, o.id, o.id,
    'scheduled', 'normal',
    '2026-03-04 08:30:00+00'::timestamptz,
    '2026-03-04 10:30:00+00'::timestamptz,
    '8 Patrick Street, Cork', 'T12 W8KP', 120
FROM users o
JOIN customers c ON c.owner_id = o.id AND c.email = 'michael.byrne@example.com'
WHERE o.email = 'owner@demo.com'
ON CONFLICT DO NOTHING;

-- Mar 5 (Thu): Active day - in_progress + scheduled
INSERT INTO jobs (title, description, customer_id, owner_id, created_by_id,
                  status, priority, start_time, end_time, location, eircode, estimated_duration, color)
SELECT
    'Thermostat Wiring Fault Diagnosis',
    'Central heating thermostat not communicating with boiler. Trace wiring fault and repair.',
    c.id, o.id, o.id,
    'in_progress', 'high',
    '2026-03-05 08:00:00+00'::timestamptz,
    '2026-03-05 10:30:00+00'::timestamptz,
    '123 Main Street, Dublin 2', 'D02 XY45', 150, '#EF4444'
FROM users o
JOIN customers c ON c.owner_id = o.id AND c.email = 'john.smith@example.com'
WHERE o.email = 'owner@demo.com'
ON CONFLICT DO NOTHING;

INSERT INTO jobs (title, description, customer_id, owner_id, created_by_id,
                  status, priority, start_time, end_time, location, eircode, estimated_duration)
SELECT
    'Commercial CCTV Maintenance',
    'Quarterly maintenance of 8-camera CCTV system. Clean lenses, check recording, update firmware.',
    c.id, o.id, o.id,
    'in_progress', 'normal',
    '2026-03-05 09:30:00+00'::timestamptz,
    '2026-03-05 12:30:00+00'::timestamptz,
    '8 Patrick Street, Cork', 'T12 W8KP', 180
FROM users o
JOIN customers c ON c.owner_id = o.id AND c.email = 'michael.byrne@example.com'
WHERE o.email = 'owner@demo.com'
ON CONFLICT DO NOTHING;

INSERT INTO jobs (title, description, customer_id, owner_id, created_by_id,
                  status, priority, start_time, end_time, location, eircode, estimated_duration)
SELECT
    'Domestic Rewire Quotation',
    'Survey 3-bed semi-detached for full rewire. Measure, photograph, and prepare quotation.',
    c.id, o.id, o.id,
    'scheduled', 'normal',
    '2026-03-05 14:00:00+00'::timestamptz,
    '2026-03-05 15:30:00+00'::timestamptz,
    '12 O''Connell Street, Limerick', 'V94 T28R', 90
FROM users o
JOIN customers c ON c.owner_id = o.id AND c.email = 'emma.kelly@example.com'
WHERE o.email = 'owner@demo.com'
ON CONFLICT DO NOTHING;

INSERT INTO jobs (title, description, customer_id, owner_id, created_by_id,
                  status, priority, start_time, end_time, location, eircode, estimated_duration, color)
SELECT
    'Intercom System Upgrade',
    'Replace old wired intercom with video intercom system. Run new cabling and configure app.',
    c.id, o.id, o.id,
    'scheduled', 'high',
    '2026-03-05 13:00:00+00'::timestamptz,
    '2026-03-05 16:00:00+00'::timestamptz,
    '45 Grafton Street, Dublin 2', 'D02 VF25', 180, '#F59E0B'
FROM users o
JOIN customers c ON c.owner_id = o.id AND c.email = 'sarah.obrien@example.com'
WHERE o.email = 'owner@demo.com'
ON CONFLICT DO NOTHING;

-- Mar 6 (Fri): Three jobs, different employees
INSERT INTO jobs (title, description, customer_id, owner_id, created_by_id,
                  status, priority, start_time, end_time, location, eircode, estimated_duration)
SELECT
    'Air Conditioning Unit Service',
    'Annual service of split-unit AC system. Clean filters, check refrigerant, test operation.',
    c.id, o.id, o.id,
    'scheduled', 'normal',
    '2026-03-06 09:00:00+00'::timestamptz,
    '2026-03-06 11:30:00+00'::timestamptz,
    '33 The Quay, Waterford', 'X91 PK12', 150
FROM users o
JOIN customers c ON c.owner_id = o.id AND c.email = 'aoife.doyle@example.com'
WHERE o.email = 'owner@demo.com'
ON CONFLICT DO NOTHING;

INSERT INTO jobs (title, description, customer_id, owner_id, created_by_id,
                  status, priority, start_time, end_time, location, eircode, estimated_duration, color)
SELECT
    'Server Room UPS Installation',
    'Install 3kVA UPS for server rack. Wire dedicated circuit and configure auto-shutdown.',
    c.id, o.id, o.id,
    'scheduled', 'high',
    '2026-03-06 08:00:00+00'::timestamptz,
    '2026-03-06 13:00:00+00'::timestamptz,
    '67 Eyre Square, Galway', 'H91 KT23', 300, '#8B5CF6'
FROM users o
JOIN customers c ON c.owner_id = o.id AND c.email = 'tom.murphy@example.com'
WHERE o.email = 'owner@demo.com'
ON CONFLICT DO NOTHING;

INSERT INTO jobs (title, description, customer_id, owner_id, created_by_id,
                  status, priority, start_time, end_time, location, eircode, estimated_duration)
SELECT
    'Cooker Circuit Installation',
    'Run new 32A cooker circuit from consumer unit. Install cooker switch and connection unit.',
    c.id, o.id, o.id,
    'scheduled', 'normal',
    '2026-03-06 10:00:00+00'::timestamptz,
    '2026-03-06 12:30:00+00'::timestamptz,
    '123 Main Street, Dublin 2', 'D02 XY45', 150
FROM users o
JOIN customers c ON c.owner_id = o.id AND c.email = 'john.smith@example.com'
WHERE o.email = 'owner@demo.com'
ON CONFLICT DO NOTHING;

-- Mar 7 (Sat): Weekend urgent job
INSERT INTO jobs (title, description, customer_id, owner_id, created_by_id,
                  status, priority, start_time, end_time, location, eircode, estimated_duration, color)
SELECT
    'Emergency Power Outage Investigation',
    'Customer reports complete power loss to property. Investigate mains supply and consumer unit.',
    c.id, o.id, o.id,
    'scheduled', 'urgent',
    '2026-03-07 08:00:00+00'::timestamptz,
    '2026-03-07 12:00:00+00'::timestamptz,
    '12 O''Connell Street, Limerick', 'V94 T28R', 240, '#DC2626'
FROM users o
JOIN customers c ON c.owner_id = o.id AND c.email = 'emma.kelly@example.com'
WHERE o.email = 'owner@demo.com'
ON CONFLICT DO NOTHING;

-- ── Week 2: Mar 9–14 ──

-- Mar 9 (Mon): Three jobs across different employees and customers
INSERT INTO jobs (title, description, customer_id, owner_id, created_by_id,
                  status, priority, start_time, end_time, location, eircode, estimated_duration, color)
SELECT
    'Electric Gate Motor Repair',
    'Sliding gate motor jammed. Strip motor, replace worn gear, re-align track, and test limits.',
    c.id, o.id, o.id,
    'scheduled', 'high',
    '2026-03-09 09:00:00+00'::timestamptz,
    '2026-03-09 12:00:00+00'::timestamptz,
    '8 Patrick Street, Cork', 'T12 W8KP', 180, '#F59E0B'
FROM users o
JOIN customers c ON c.owner_id = o.id AND c.email = 'michael.byrne@example.com'
WHERE o.email = 'owner@demo.com'
ON CONFLICT DO NOTHING;

INSERT INTO jobs (title, description, customer_id, owner_id, created_by_id,
                  status, priority, start_time, end_time, location, eircode, estimated_duration, color)
SELECT
    'Office LED Lighting Retrofit',
    'Replace 24 fluorescent fittings with LED panels. Rewire and dispose of old ballasts.',
    c.id, o.id, o.id,
    'scheduled', 'low',
    '2026-03-09 10:00:00+00'::timestamptz,
    '2026-03-09 13:00:00+00'::timestamptz,
    '67 Eyre Square, Galway', 'H91 KT23', 180, '#10B981'
FROM users o
JOIN customers c ON c.owner_id = o.id AND c.email = 'tom.murphy@example.com'
WHERE o.email = 'owner@demo.com'
ON CONFLICT DO NOTHING;

INSERT INTO jobs (title, description, customer_id, owner_id, created_by_id,
                  status, priority, start_time, end_time, location, eircode, estimated_duration)
SELECT
    'Earthing System Test',
    'Earth resistance testing using fall-of-potential method. Issue test report.',
    c.id, o.id, o.id,
    'scheduled', 'normal',
    '2026-03-09 09:00:00+00'::timestamptz,
    '2026-03-09 11:00:00+00'::timestamptz,
    '12 O''Connell Street, Limerick', 'V94 T28R', 120
FROM users o
JOIN customers c ON c.owner_id = o.id AND c.email = 'emma.kelly@example.com'
WHERE o.email = 'owner@demo.com'
ON CONFLICT DO NOTHING;

-- Mar 10–12 (Tue–Thu): Multi-day apartment rewire + daily jobs
INSERT INTO jobs (title, description, customer_id, owner_id, created_by_id,
                  status, priority, start_time, end_time, location, eircode, estimated_duration, color)
SELECT
    'Apartment Block Rewire - Block A',
    'Full rewire of 4 apartments in Block A. Replace all circuits, fit new consumer units and test.',
    c.id, o.id, o.id,
    'scheduled', 'high',
    '2026-03-10 08:00:00+00'::timestamptz,
    '2026-03-12 17:00:00+00'::timestamptz,
    '67 Eyre Square, Galway', 'H91 KT23', 1500, '#8B5CF6'
FROM users o
JOIN customers c ON c.owner_id = o.id AND c.email = 'tom.murphy@example.com'
WHERE o.email = 'owner@demo.com'
ON CONFLICT DO NOTHING;

INSERT INTO jobs (title, description, customer_id, owner_id, created_by_id,
                  status, priority, start_time, end_time, location, eircode, estimated_duration)
SELECT
    'Cable Trunking Installation',
    'Install 30m of PVC trunking along office perimeter for new desktop sockets.',
    c.id, o.id, o.id,
    'scheduled', 'normal',
    '2026-03-10 09:00:00+00'::timestamptz,
    '2026-03-10 12:00:00+00'::timestamptz,
    '123 Main Street, Dublin 2', 'D02 XY45', 180
FROM users o
JOIN customers c ON c.owner_id = o.id AND c.email = 'john.smith@example.com'
WHERE o.email = 'owner@demo.com'
ON CONFLICT DO NOTHING;

INSERT INTO jobs (title, description, customer_id, owner_id, created_by_id,
                  status, priority, start_time, end_time, location, eircode, estimated_duration, color)
SELECT
    'PAT Testing - Office Equipment',
    'Portable appliance testing for 80 items across two office floors. Label and log results.',
    c.id, o.id, o.id,
    'scheduled', 'low',
    '2026-03-10 13:00:00+00'::timestamptz,
    '2026-03-10 16:00:00+00'::timestamptz,
    '33 The Quay, Waterford', 'X91 PK12', 180, '#10B981'
FROM users o
JOIN customers c ON c.owner_id = o.id AND c.email = 'aoife.doyle@example.com'
WHERE o.email = 'owner@demo.com'
ON CONFLICT DO NOTHING;

-- Mar 11 (Wed)
INSERT INTO jobs (title, description, customer_id, owner_id, created_by_id,
                  status, priority, start_time, end_time, location, eircode, estimated_duration, color)
SELECT
    'Doorbell Camera Installation',
    'Install Ring Video Doorbell Pro. Run low-voltage wiring and configure WiFi app.',
    c.id, o.id, o.id,
    'scheduled', 'low',
    '2026-03-11 10:00:00+00'::timestamptz,
    '2026-03-11 11:30:00+00'::timestamptz,
    '12 O''Connell Street, Limerick', 'V94 T28R', 90, '#10B981'
FROM users o
JOIN customers c ON c.owner_id = o.id AND c.email = 'emma.kelly@example.com'
WHERE o.email = 'owner@demo.com'
ON CONFLICT DO NOTHING;

INSERT INTO jobs (title, description, customer_id, owner_id, created_by_id,
                  status, priority, start_time, end_time, location, eircode, estimated_duration)
SELECT
    'Immersion Timer Replacement',
    'Replace mechanical immersion timer with digital 7-day programmer.',
    c.id, o.id, o.id,
    'scheduled', 'normal',
    '2026-03-11 14:00:00+00'::timestamptz,
    '2026-03-11 15:30:00+00'::timestamptz,
    '45 Grafton Street, Dublin 2', 'D02 VF25', 90
FROM users o
JOIN customers c ON c.owner_id = o.id AND c.email = 'sarah.obrien@example.com'
WHERE o.email = 'owner@demo.com'
ON CONFLICT DO NOTHING;

-- Mar 12 (Thu): Busy day - 3 jobs
INSERT INTO jobs (title, description, customer_id, owner_id, created_by_id,
                  status, priority, start_time, end_time, location, eircode, estimated_duration, color)
SELECT
    'Distribution Board Upgrade',
    'Replace old rewireable fuse board with modern 18-way RCBO consumer unit. RECI cert required.',
    c.id, o.id, o.id,
    'scheduled', 'urgent',
    '2026-03-12 08:00:00+00'::timestamptz,
    '2026-03-12 12:00:00+00'::timestamptz,
    '8 Patrick Street, Cork', 'T12 W8KP', 240, '#DC2626'
FROM users o
JOIN customers c ON c.owner_id = o.id AND c.email = 'michael.byrne@example.com'
WHERE o.email = 'owner@demo.com'
ON CONFLICT DO NOTHING;

INSERT INTO jobs (title, description, customer_id, owner_id, created_by_id,
                  status, priority, start_time, end_time, location, eircode, estimated_duration)
SELECT
    'Dimmer Switch Installation x6',
    'Replace 6 standard light switches with LED-compatible dimmer switches throughout house.',
    c.id, o.id, o.id,
    'scheduled', 'low',
    '2026-03-12 09:00:00+00'::timestamptz,
    '2026-03-12 11:00:00+00'::timestamptz,
    '123 Main Street, Dublin 2', 'D02 XY45', 120
FROM users o
JOIN customers c ON c.owner_id = o.id AND c.email = 'john.smith@example.com'
WHERE o.email = 'owner@demo.com'
ON CONFLICT DO NOTHING;

INSERT INTO jobs (title, description, customer_id, owner_id, created_by_id,
                  status, priority, start_time, end_time, location, eircode, estimated_duration, color)
SELECT
    'Garden Floodlight Setup',
    'Install 4 adjustable LED floodlights around garden perimeter with dusk-to-dawn sensors.',
    c.id, o.id, o.id,
    'scheduled', 'normal',
    '2026-03-12 13:00:00+00'::timestamptz,
    '2026-03-12 15:30:00+00'::timestamptz,
    '33 The Quay, Waterford', 'X91 PK12', 150, '#3B82F6'
FROM users o
JOIN customers c ON c.owner_id = o.id AND c.email = 'aoife.doyle@example.com'
WHERE o.email = 'owner@demo.com'
ON CONFLICT DO NOTHING;

-- Mar 13 (Fri): Mixed statuses - on_hold + cancelled + scheduled
INSERT INTO jobs (title, description, customer_id, owner_id, created_by_id,
                  status, priority, start_time, end_time, location, eircode, estimated_duration, color)
SELECT
    'Sauna Electrical Hookup',
    'On hold - waiting for building control sign-off before proceeding with sauna power supply.',
    c.id, o.id, o.id,
    'on_hold', 'normal',
    '2026-03-13 09:00:00+00'::timestamptz,
    '2026-03-13 12:00:00+00'::timestamptz,
    '45 Grafton Street, Dublin 2', 'D02 VF25', 180, '#6B7280'
FROM users o
JOIN customers c ON c.owner_id = o.id AND c.email = 'sarah.obrien@example.com'
WHERE o.email = 'owner@demo.com'
ON CONFLICT DO NOTHING;

INSERT INTO jobs (title, description, customer_id, owner_id, created_by_id,
                  status, priority, start_time, end_time, location, eircode, estimated_duration)
SELECT
    'Roof Solar Panel Wiring',
    'Cancelled - planning permission denied for solar panel installation on listed building.',
    c.id, o.id, o.id,
    'cancelled', 'high',
    '2026-03-13 10:00:00+00'::timestamptz,
    '2026-03-13 15:00:00+00'::timestamptz,
    '8 Patrick Street, Cork', 'T12 W8KP', 300
FROM users o
JOIN customers c ON c.owner_id = o.id AND c.email = 'michael.byrne@example.com'
WHERE o.email = 'owner@demo.com'
ON CONFLICT DO NOTHING;

INSERT INTO jobs (title, description, customer_id, owner_id, created_by_id,
                  status, priority, start_time, end_time, location, eircode, estimated_duration)
SELECT
    'Electric Shower Installation',
    'Install 10.5kW electric shower. Run 10mm² cable from consumer unit and fit MCB.',
    c.id, o.id, o.id,
    'scheduled', 'normal',
    '2026-03-13 10:00:00+00'::timestamptz,
    '2026-03-13 12:30:00+00'::timestamptz,
    '67 Eyre Square, Galway', 'H91 KT23', 150
FROM users o
JOIN customers c ON c.owner_id = o.id AND c.email = 'tom.murphy@example.com'
WHERE o.email = 'owner@demo.com'
ON CONFLICT DO NOTHING;

-- Mar 14 (Sat): Weekend high-priority job
INSERT INTO jobs (title, description, customer_id, owner_id, created_by_id,
                  status, priority, start_time, end_time, location, eircode, estimated_duration, color)
SELECT
    'Shopping Centre Emergency Lighting Test',
    'Six-monthly emergency lighting test. Activate all 48 units, log results, replace failed bulbs.',
    c.id, o.id, o.id,
    'scheduled', 'high',
    '2026-03-14 07:00:00+00'::timestamptz,
    '2026-03-14 11:00:00+00'::timestamptz,
    '8 Patrick Street, Cork', 'T12 W8KP', 240, '#F59E0B'
FROM users o
JOIN customers c ON c.owner_id = o.id AND c.email = 'michael.byrne@example.com'
WHERE o.email = 'owner@demo.com'
ON CONFLICT DO NOTHING;

-- ── Week 3: Mar 16–21 (Phase 2 rewiring already seeded for employee@demo.com) ──

-- Mar 16 (Mon): Other employees work while Phase 2 runs
INSERT INTO jobs (title, description, customer_id, owner_id, created_by_id,
                  status, priority, start_time, end_time, location, eircode, estimated_duration)
SELECT
    'Underfloor Heating Wiring',
    'Wire UFH manifold and thermostat zones for 4 rooms. Connect to existing boiler controls.',
    c.id, o.id, o.id,
    'scheduled', 'normal',
    '2026-03-16 09:00:00+00'::timestamptz,
    '2026-03-16 17:00:00+00'::timestamptz,
    '123 Main Street, Dublin 2', 'D02 XY45', 480
FROM users o
JOIN customers c ON c.owner_id = o.id AND c.email = 'john.smith@example.com'
WHERE o.email = 'owner@demo.com'
ON CONFLICT DO NOTHING;

-- Mar 17 (Tue)
INSERT INTO jobs (title, description, customer_id, owner_id, created_by_id,
                  status, priority, start_time, end_time, location, eircode, estimated_duration, color)
SELECT
    'Retail LED Lighting Upgrade',
    'Replace all display lighting with dimmable LED track lights. 3 zones with separate controls.',
    c.id, o.id, o.id,
    'scheduled', 'high',
    '2026-03-17 08:00:00+00'::timestamptz,
    '2026-03-17 16:00:00+00'::timestamptz,
    '67 Eyre Square, Galway', 'H91 KT23', 480, '#F59E0B'
FROM users o
JOIN customers c ON c.owner_id = o.id AND c.email = 'tom.murphy@example.com'
WHERE o.email = 'owner@demo.com'
ON CONFLICT DO NOTHING;

-- Mar 18 (Wed)
INSERT INTO jobs (title, description, customer_id, owner_id, created_by_id,
                  status, priority, start_time, end_time, location, eircode, estimated_duration, color)
SELECT
    'EV Charger Installation',
    'Install 7.4kW Type 2 EV charger in driveway. Dedicated circuit from consumer unit, SEAI grant.',
    c.id, o.id, o.id,
    'scheduled', 'normal',
    '2026-03-18 10:00:00+00'::timestamptz,
    '2026-03-18 15:00:00+00'::timestamptz,
    '45 Grafton Street, Dublin 2', 'D02 VF25', 300, '#3B82F6'
FROM users o
JOIN customers c ON c.owner_id = o.id AND c.email = 'sarah.obrien@example.com'
WHERE o.email = 'owner@demo.com'
ON CONFLICT DO NOTHING;

-- Mar 19 (Thu)
INSERT INTO jobs (title, description, customer_id, owner_id, created_by_id,
                  status, priority, start_time, end_time, location, eircode, estimated_duration)
SELECT
    'Temporary Site Power Setup',
    'Install temporary DB and 3 socket outlets for building contractor. 30m armoured cable run.',
    c.id, o.id, o.id,
    'scheduled', 'normal',
    '2026-03-19 09:00:00+00'::timestamptz,
    '2026-03-19 13:00:00+00'::timestamptz,
    '33 The Quay, Waterford', 'X91 PK12', 240
FROM users o
JOIN customers c ON c.owner_id = o.id AND c.email = 'aoife.doyle@example.com'
WHERE o.email = 'owner@demo.com'
ON CONFLICT DO NOTHING;

-- Mar 20 (Fri): Three jobs
INSERT INTO jobs (title, description, customer_id, owner_id, created_by_id,
                  status, priority, start_time, end_time, location, eircode, estimated_duration, color)
SELECT
    'BER Energy Assessment',
    'Full Building Energy Rating assessment for sale of property. Inspect insulation, heating, lighting.',
    c.id, o.id, o.id,
    'scheduled', 'low',
    '2026-03-20 09:00:00+00'::timestamptz,
    '2026-03-20 11:00:00+00'::timestamptz,
    '67 Eyre Square, Galway', 'H91 KT23', 120, '#10B981'
FROM users o
JOIN customers c ON c.owner_id = o.id AND c.email = 'tom.murphy@example.com'
WHERE o.email = 'owner@demo.com'
ON CONFLICT DO NOTHING;

INSERT INTO jobs (title, description, customer_id, owner_id, created_by_id,
                  status, priority, start_time, end_time, location, eircode, estimated_duration, color)
SELECT
    'Industrial Motor Starter Replacement',
    'Replace burned-out DOL starter on warehouse conveyor motor. Source part, wire in, and test.',
    c.id, o.id, o.id,
    'scheduled', 'urgent',
    '2026-03-20 08:00:00+00'::timestamptz,
    '2026-03-20 15:00:00+00'::timestamptz,
    '8 Patrick Street, Cork', 'T12 W8KP', 420, '#DC2626'
FROM users o
JOIN customers c ON c.owner_id = o.id AND c.email = 'michael.byrne@example.com'
WHERE o.email = 'owner@demo.com'
ON CONFLICT DO NOTHING;

INSERT INTO jobs (title, description, customer_id, owner_id, created_by_id,
                  status, priority, start_time, end_time, location, eircode, estimated_duration)
SELECT
    'Smart Meter Upgrade',
    'Upgrade traditional electricity meter to smart meter. Test communications and verify readings.',
    c.id, o.id, o.id,
    'scheduled', 'normal',
    '2026-03-20 14:00:00+00'::timestamptz,
    '2026-03-20 16:00:00+00'::timestamptz,
    '123 Main Street, Dublin 2', 'D02 XY45', 120
FROM users o
JOIN customers c ON c.owner_id = o.id AND c.email = 'john.smith@example.com'
WHERE o.email = 'owner@demo.com'
ON CONFLICT DO NOTHING;

-- Mar 21 (Sat): Weekend job
INSERT INTO jobs (title, description, customer_id, owner_id, created_by_id,
                  status, priority, start_time, end_time, location, eircode, estimated_duration, color)
SELECT
    'Marquee Lighting Setup',
    'Install festoon and uplighting in garden marquee for wedding. Temporary supply from house DB.',
    c.id, o.id, o.id,
    'scheduled', 'low',
    '2026-03-21 10:00:00+00'::timestamptz,
    '2026-03-21 13:00:00+00'::timestamptz,
    '45 Grafton Street, Dublin 2', 'D02 VF25', 180, '#EC4899'
FROM users o
JOIN customers c ON c.owner_id = o.id AND c.email = 'sarah.obrien@example.com'
WHERE o.email = 'owner@demo.com'
ON CONFLICT DO NOTHING;

-- ── Week 4: Mar 23–28 ──

-- Mar 23 (Mon): 3 regular + 1 all-day event
INSERT INTO jobs (title, description, customer_id, owner_id, created_by_id,
                  status, priority, start_time, end_time, location, eircode, estimated_duration, color)
SELECT
    'Backup Generator Service',
    'Annual service of 20kVA diesel generator. Oil change, filter, battery test, load bank test.',
    c.id, o.id, o.id,
    'scheduled', 'high',
    '2026-03-23 08:00:00+00'::timestamptz,
    '2026-03-23 12:00:00+00'::timestamptz,
    '8 Patrick Street, Cork', 'T12 W8KP', 240, '#F59E0B'
FROM users o
JOIN customers c ON c.owner_id = o.id AND c.email = 'michael.byrne@example.com'
WHERE o.email = 'owner@demo.com'
ON CONFLICT DO NOTHING;

INSERT INTO jobs (title, description, customer_id, owner_id, created_by_id,
                  status, priority, start_time, end_time, location, eircode, estimated_duration)
SELECT
    'Bathroom Heated Towel Rail Wiring',
    'Wire fused spur for new electric heated towel rail in en-suite bathroom.',
    c.id, o.id, o.id,
    'scheduled', 'low',
    '2026-03-23 09:00:00+00'::timestamptz,
    '2026-03-23 10:30:00+00'::timestamptz,
    '123 Main Street, Dublin 2', 'D02 XY45', 90
FROM users o
JOIN customers c ON c.owner_id = o.id AND c.email = 'john.smith@example.com'
WHERE o.email = 'owner@demo.com'
ON CONFLICT DO NOTHING;

INSERT INTO jobs (title, description, customer_id, owner_id, created_by_id,
                  status, priority, start_time, end_time, location, eircode, estimated_duration, color)
SELECT
    'Office Network Patch Panel',
    'Install 24-port patch panel in comms cabinet. Terminate and test all Cat6a connections.',
    c.id, o.id, o.id,
    'scheduled', 'normal',
    '2026-03-23 10:00:00+00'::timestamptz,
    '2026-03-23 15:00:00+00'::timestamptz,
    '33 The Quay, Waterford', 'X91 PK12', 300, '#3B82F6'
FROM users o
JOIN customers c ON c.owner_id = o.id AND c.email = 'aoife.doyle@example.com'
WHERE o.email = 'owner@demo.com'
ON CONFLICT DO NOTHING;

INSERT INTO jobs (title, description, customer_id, owner_id, created_by_id,
                  status, priority, start_time, end_time, all_day, location, eircode, estimated_duration, color)
SELECT
    'Fire Safety Compliance Audit',
    'Full-day audit of fire alarm, emergency lighting, and extinguisher compliance across all units.',
    c.id, o.id, o.id,
    'scheduled', 'high',
    '2026-03-23 00:00:00+00'::timestamptz,
    '2026-03-23 23:59:59+00'::timestamptz,
    TRUE,
    '67 Eyre Square, Galway', 'H91 KT23', 480, '#EF4444'
FROM users o
JOIN customers c ON c.owner_id = o.id AND c.email = 'tom.murphy@example.com'
WHERE o.email = 'owner@demo.com'
ON CONFLICT DO NOTHING;

-- Mar 24 (Tue): 1 all-day + 2 regular
INSERT INTO jobs (title, description, customer_id, owner_id, created_by_id,
                  status, priority, start_time, end_time, all_day, location, eircode, estimated_duration, color)
SELECT
    'Warehouse Full Electrical Audit',
    'Comprehensive audit of warehouse electrical systems per ETCI rules. Full report and cert.',
    c.id, o.id, o.id,
    'scheduled', 'high',
    '2026-03-24 00:00:00+00'::timestamptz,
    '2026-03-24 23:59:59+00'::timestamptz,
    TRUE,
    '8 Patrick Street, Cork', 'T12 W8KP', 480, '#F59E0B'
FROM users o
JOIN customers c ON c.owner_id = o.id AND c.email = 'michael.byrne@example.com'
WHERE o.email = 'owner@demo.com'
ON CONFLICT DO NOTHING;

INSERT INTO jobs (title, description, customer_id, owner_id, created_by_id,
                  status, priority, start_time, end_time, location, eircode, estimated_duration)
SELECT
    'Motion Sensor Light Installation',
    'Install PIR motion sensor floodlights at front and rear of property. Wire to existing circuits.',
    c.id, o.id, o.id,
    'scheduled', 'normal',
    '2026-03-24 13:00:00+00'::timestamptz,
    '2026-03-24 15:00:00+00'::timestamptz,
    '123 Main Street, Dublin 2', 'D02 XY45', 120
FROM users o
JOIN customers c ON c.owner_id = o.id AND c.email = 'john.smith@example.com'
WHERE o.email = 'owner@demo.com'
ON CONFLICT DO NOTHING;

INSERT INTO jobs (title, description, customer_id, owner_id, created_by_id,
                  status, priority, start_time, end_time, location, eircode, estimated_duration)
SELECT
    'Garage Consumer Unit Upgrade',
    'Upgrade single-way fusebox in detached garage to 6-way consumer unit with RCD protection.',
    c.id, o.id, o.id,
    'scheduled', 'normal',
    '2026-03-24 09:00:00+00'::timestamptz,
    '2026-03-24 12:00:00+00'::timestamptz,
    '33 The Quay, Waterford', 'X91 PK12', 180
FROM users o
JOIN customers c ON c.owner_id = o.id AND c.email = 'aoife.doyle@example.com'
WHERE o.email = 'owner@demo.com'
ON CONFLICT DO NOTHING;

-- Mar 25–27: Multi-day job + regular daily jobs
INSERT INTO jobs (title, description, customer_id, owner_id, created_by_id,
                  status, priority, start_time, end_time, location, eircode, estimated_duration, color)
SELECT
    'New Build Pre-Wire - Phase 1',
    'First-fix electrical for 3-bed new build. Lay all cables, back boxes, and conduit before plastering.',
    c.id, o.id, o.id,
    'scheduled', 'high',
    '2026-03-25 08:00:00+00'::timestamptz,
    '2026-03-27 17:00:00+00'::timestamptz,
    '67 Eyre Square, Galway', 'H91 KT23', 1440, '#8B5CF6'
FROM users o
JOIN customers c ON c.owner_id = o.id AND c.email = 'tom.murphy@example.com'
WHERE o.email = 'owner@demo.com'
ON CONFLICT DO NOTHING;

INSERT INTO jobs (title, description, customer_id, owner_id, created_by_id,
                  status, priority, start_time, end_time, location, eircode, estimated_duration)
SELECT
    'CCTV Hard Drive Replacement',
    'Replace failed 4TB HDD in NVR. Reconfigure recording schedule and verify all camera feeds.',
    c.id, o.id, o.id,
    'scheduled', 'normal',
    '2026-03-25 09:00:00+00'::timestamptz,
    '2026-03-25 11:00:00+00'::timestamptz,
    '123 Main Street, Dublin 2', 'D02 XY45', 120
FROM users o
JOIN customers c ON c.owner_id = o.id AND c.email = 'john.smith@example.com'
WHERE o.email = 'owner@demo.com'
ON CONFLICT DO NOTHING;

-- Mar 26 (Thu)
INSERT INTO jobs (title, description, customer_id, owner_id, created_by_id,
                  status, priority, start_time, end_time, location, eircode, estimated_duration)
SELECT
    'Staircase LED Strip Lighting',
    'Install LED strip lighting under staircase nosings with motion sensor control. 14 treads.',
    c.id, o.id, o.id,
    'scheduled', 'normal',
    '2026-03-26 10:00:00+00'::timestamptz,
    '2026-03-26 14:00:00+00'::timestamptz,
    '45 Grafton Street, Dublin 2', 'D02 VF25', 240
FROM users o
JOIN customers c ON c.owner_id = o.id AND c.email = 'sarah.obrien@example.com'
WHERE o.email = 'owner@demo.com'
ON CONFLICT DO NOTHING;

INSERT INTO jobs (title, description, customer_id, owner_id, created_by_id,
                  status, priority, start_time, end_time, location, eircode, estimated_duration, color)
SELECT
    'Emergency Light Battery Swap',
    'Replace NiCd batteries in 12 emergency light fittings. Test 3-hour duration compliance.',
    c.id, o.id, o.id,
    'scheduled', 'low',
    '2026-03-26 15:00:00+00'::timestamptz,
    '2026-03-26 16:30:00+00'::timestamptz,
    '12 O''Connell Street, Limerick', 'V94 T28R', 90, '#10B981'
FROM users o
JOIN customers c ON c.owner_id = o.id AND c.email = 'emma.kelly@example.com'
WHERE o.email = 'owner@demo.com'
ON CONFLICT DO NOTHING;

-- Mar 27 (Fri)
INSERT INTO jobs (title, description, customer_id, owner_id, created_by_id,
                  status, priority, start_time, end_time, location, eircode, estimated_duration, color)
SELECT
    'Hot Tub Electrical Connection',
    'Install dedicated 32A supply for outdoor hot tub. IP65 isolator, armoured cable, RCD protection.',
    c.id, o.id, o.id,
    'scheduled', 'high',
    '2026-03-27 13:00:00+00'::timestamptz,
    '2026-03-27 16:00:00+00'::timestamptz,
    '45 Grafton Street, Dublin 2', 'D02 VF25', 180, '#F59E0B'
FROM users o
JOIN customers c ON c.owner_id = o.id AND c.email = 'sarah.obrien@example.com'
WHERE o.email = 'owner@demo.com'
ON CONFLICT DO NOTHING;

INSERT INTO jobs (title, description, customer_id, owner_id, created_by_id,
                  status, priority, start_time, end_time, location, eircode, estimated_duration)
SELECT
    'Kitchen Socket Repositioning',
    'Move 4 double sockets above new worktop height. Chase walls, re-route cables, make good.',
    c.id, o.id, o.id,
    'scheduled', 'normal',
    '2026-03-27 09:00:00+00'::timestamptz,
    '2026-03-27 12:00:00+00'::timestamptz,
    '33 The Quay, Waterford', 'X91 PK12', 180
FROM users o
JOIN customers c ON c.owner_id = o.id AND c.email = 'aoife.doyle@example.com'
WHERE o.email = 'owner@demo.com'
ON CONFLICT DO NOTHING;

-- Mar 28 (Sat): Weekend emergency
INSERT INTO jobs (title, description, customer_id, owner_id, created_by_id,
                  status, priority, start_time, end_time, location, eircode, estimated_duration, color)
SELECT
    'Weekend Emergency - Tripped RCD',
    'Customer RCD keeps tripping. Isolate circuits one by one to find fault. Likely outdoor socket.',
    c.id, o.id, o.id,
    'scheduled', 'urgent',
    '2026-03-28 11:00:00+00'::timestamptz,
    '2026-03-28 12:30:00+00'::timestamptz,
    '12 O''Connell Street, Limerick', 'V94 T28R', 90, '#DC2626'
FROM users o
JOIN customers c ON c.owner_id = o.id AND c.email = 'emma.kelly@example.com'
WHERE o.email = 'owner@demo.com'
ON CONFLICT DO NOTHING;

-- ── Week 5: Mar 30–31 ──

-- Mar 30 (Mon): End of month - 3 jobs
INSERT INTO jobs (title, description, customer_id, owner_id, created_by_id,
                  status, priority, start_time, end_time, location, eircode, estimated_duration, color)
SELECT
    'Annual Electrical Safety Cert',
    'Full RECI periodic inspection and testing for commercial premises. Issue Completion Cert.',
    c.id, o.id, o.id,
    'scheduled', 'high',
    '2026-03-30 08:00:00+00'::timestamptz,
    '2026-03-30 17:00:00+00'::timestamptz,
    '8 Patrick Street, Cork', 'T12 W8KP', 540, '#F59E0B'
FROM users o
JOIN customers c ON c.owner_id = o.id AND c.email = 'michael.byrne@example.com'
WHERE o.email = 'owner@demo.com'
ON CONFLICT DO NOTHING;

INSERT INTO jobs (title, description, customer_id, owner_id, created_by_id,
                  status, priority, start_time, end_time, location, eircode, estimated_duration, color)
SELECT
    'Conference Room AV Wiring',
    'Run HDMI, USB-C, and network cables to conference table. Install floor box and wall plates.',
    c.id, o.id, o.id,
    'scheduled', 'normal',
    '2026-03-30 10:00:00+00'::timestamptz,
    '2026-03-30 14:00:00+00'::timestamptz,
    '33 The Quay, Waterford', 'X91 PK12', 240, '#3B82F6'
FROM users o
JOIN customers c ON c.owner_id = o.id AND c.email = 'aoife.doyle@example.com'
WHERE o.email = 'owner@demo.com'
ON CONFLICT DO NOTHING;

INSERT INTO jobs (title, description, customer_id, owner_id, created_by_id,
                  status, priority, start_time, end_time, location, eircode, estimated_duration)
SELECT
    'Outdoor Security Lighting',
    'Install 6 PIR security lights around property perimeter. Dusk-to-dawn with override switch.',
    c.id, o.id, o.id,
    'scheduled', 'normal',
    '2026-03-30 13:00:00+00'::timestamptz,
    '2026-03-30 16:00:00+00'::timestamptz,
    '67 Eyre Square, Galway', 'H91 KT23', 180
FROM users o
JOIN customers c ON c.owner_id = o.id AND c.email = 'tom.murphy@example.com'
WHERE o.email = 'owner@demo.com'
ON CONFLICT DO NOTHING;

-- Mar 31 (Tue): Last day of month - 3 jobs
INSERT INTO jobs (title, description, customer_id, owner_id, created_by_id,
                  status, priority, start_time, end_time, location, eircode, estimated_duration, color)
SELECT
    'End-of-Quarter Equipment Inspection',
    'Inspect all power tools and test equipment. PAT test, calibrate, log serial numbers.',
    c.id, o.id, o.id,
    'scheduled', 'high',
    '2026-03-31 09:00:00+00'::timestamptz,
    '2026-03-31 12:00:00+00'::timestamptz,
    '8 Patrick Street, Cork', 'T12 W8KP', 180, '#8B5CF6'
FROM users o
JOIN customers c ON c.owner_id = o.id AND c.email = 'michael.byrne@example.com'
WHERE o.email = 'owner@demo.com'
ON CONFLICT DO NOTHING;

INSERT INTO jobs (title, description, customer_id, owner_id, created_by_id,
                  status, priority, start_time, end_time, location, eircode, estimated_duration)
SELECT
    'Electric Fence Controller Repair',
    'Energiser unit not producing output. Test transformer, capacitor, and fence line. Replace unit if needed.',
    c.id, o.id, o.id,
    'scheduled', 'normal',
    '2026-03-31 13:00:00+00'::timestamptz,
    '2026-03-31 15:00:00+00'::timestamptz,
    '12 O''Connell Street, Limerick', 'V94 T28R', 120
FROM users o
JOIN customers c ON c.owner_id = o.id AND c.email = 'emma.kelly@example.com'
WHERE o.email = 'owner@demo.com'
ON CONFLICT DO NOTHING;

INSERT INTO jobs (title, description, owner_id, created_by_id,
                  status, priority, start_time, end_time, location, estimated_duration, color)
SELECT
    'Month-End Timesheet & Invoice Review',
    'Review all March timesheets, prepare invoices for completed jobs, update job costings.',
    o.id, o.id,
    'scheduled', 'low',
    '2026-03-31 15:00:00+00'::timestamptz,
    '2026-03-31 17:00:00+00'::timestamptz,
    'Office - 456 Business Park, Dublin', 120, '#6B7280'
FROM users o
WHERE o.email = 'owner@demo.com'
ON CONFLICT DO NOTHING;

-- ──────────────────────────────────────────
-- Overlapping multi-day jobs & all-day events (calendar stress-test)
-- ──────────────────────────────────────────

-- Overlaps with "Full House Rewiring - Phase 2" (Mar 16–19, employee@demo.com)
INSERT INTO jobs (title, description, customer_id, owner_id, created_by_id,
                  status, priority, start_time, end_time, location, eircode, estimated_duration, color)
SELECT
    'Commercial Fit-Out - Electrical Package',
    'Full electrical fit-out for new office suite. Lighting, power, data cabling across 3 floors.',
    c.id, o.id, o.id,
    'scheduled', 'high',
    '2026-03-16 08:30:00+00'::timestamptz,
    '2026-03-18 17:00:00+00'::timestamptz,
    '22 Grafton Street, Dublin 2', 'D02 HK56', 1440, '#10B981'
FROM users o
JOIN customers c ON c.owner_id = o.id AND c.email = 'sarah.obrien@example.com'
WHERE o.email = 'owner@demo.com'
ON CONFLICT DO NOTHING;

-- Also overlaps Mar 16–19 range (employee3 / Liam Murphy)
INSERT INTO jobs (title, description, customer_id, owner_id, created_by_id,
                  status, priority, start_time, end_time, location, eircode, estimated_duration, color)
SELECT
    'School Summer Works - Rewire Block B',
    'Full rewire of 8 classrooms and corridors in Block B. First-fix before summer end.',
    c.id, o.id, o.id,
    'in_progress', 'urgent',
    '2026-03-17 07:30:00+00'::timestamptz,
    '2026-03-20 16:30:00+00'::timestamptz,
    '15 Seatown Road, Dundalk', 'A91 X2T7', 1800, '#EF4444'
FROM users o
JOIN customers c ON c.owner_id = o.id AND c.email = 'aoife.doyle@example.com'
WHERE o.email = 'owner@demo.com'
ON CONFLICT DO NOTHING;

-- Overlaps with "New Build Pre-Wire - Phase 1" (Mar 25–27, employee@demo.com)
INSERT INTO jobs (title, description, customer_id, owner_id, created_by_id,
                  status, priority, start_time, end_time, location, eircode, estimated_duration, color)
SELECT
    'Hotel Ballroom Lighting Refit',
    'Replace chandeliers and install DMX dimming system in main ballroom and foyer.',
    c.id, o.id, o.id,
    'scheduled', 'high',
    '2026-03-25 09:00:00+00'::timestamptz,
    '2026-03-27 18:00:00+00'::timestamptz,
    '5 Eyre Square, Galway', 'H91 RD45', 1440, '#F59E0B'
FROM users o
JOIN customers c ON c.owner_id = o.id AND c.email = 'tom.murphy@example.com'
WHERE o.email = 'owner@demo.com'
ON CONFLICT DO NOTHING;

-- Second all-day event on Mar 23 (overlaps with "Fire Safety Compliance Audit", employee2)
INSERT INTO jobs (title, description, customer_id, owner_id, created_by_id,
                  status, priority, start_time, end_time, all_day, location, eircode, estimated_duration, color)
SELECT
    'Annual PAT Testing - Full Site',
    'Portable appliance testing for all equipment across warehouse and offices. Full day on-site.',
    c.id, o.id, o.id,
    'scheduled', 'normal',
    '2026-03-23 00:00:00+00'::timestamptz,
    '2026-03-23 23:59:59+00'::timestamptz,
    TRUE,
    '8 Patrick Street, Cork', 'T12 W8KP', 480, '#3B82F6'
FROM users o
JOIN customers c ON c.owner_id = o.id AND c.email = 'michael.byrne@example.com'
WHERE o.email = 'owner@demo.com'
ON CONFLICT DO NOTHING;

-- Third all-day event on Mar 23 (tests 3-lane stacking in week view)
INSERT INTO jobs (title, description, customer_id, owner_id, created_by_id,
                  status, priority, start_time, end_time, all_day, location, eircode, estimated_duration, color)
SELECT
    'Emergency Lighting Certification - All Buildings',
    'Annual emergency lighting duration test and certification across all tenant buildings.',
    c.id, o.id, o.id,
    'scheduled', 'high',
    '2026-03-23 00:00:00+00'::timestamptz,
    '2026-03-23 23:59:59+00'::timestamptz,
    TRUE,
    '33 The Quay, Waterford', 'X91 PK12', 480, '#8B5CF6'
FROM users o
JOIN customers c ON c.owner_id = o.id AND c.email = 'aoife.doyle@example.com'
WHERE o.email = 'owner@demo.com'
ON CONFLICT DO NOTHING;

-- ──────────────────────────────────────────
-- April 1 2026 - Full day for employee@demo.com (demo day)
-- ──────────────────────────────────────────

-- Job 1: 08:30–10:00 - Morning call-out
INSERT INTO jobs (title, description, customer_id, owner_id, created_by_id,
                  status, priority, start_time, end_time, location, eircode, estimated_duration, color, latitude, longitude)
SELECT
    'Smoke Alarm Replacement - Residential',
    'Replace expired smoke alarms in hallway, kitchen and bedrooms. Test interconnect wiring.',
    c.id, o.id, o.id,
    'scheduled', 'high',
    '2026-04-01 08:30:00+00'::timestamptz,
    '2026-04-01 10:00:00+00'::timestamptz,
    '15 Pembroke Road, Dublin 4', 'D04 N2R7', 90, '#EF4444', 53.3244, -6.2406
FROM users o
JOIN customers c ON c.owner_id = o.id AND c.email = 'john.smith@example.com'
WHERE o.email = 'owner@demo.com'
ON CONFLICT DO NOTHING;

-- Job 2: 10:30–12:30 - Mid-morning
INSERT INTO jobs (title, description, customer_id, owner_id, created_by_id,
                  status, priority, start_time, end_time, location, eircode, estimated_duration, color, latitude, longitude)
SELECT
    'Outdoor Patio Lighting Setup',
    'Install 6 low-voltage LED garden lights along patio path and wire back to garage consumer unit.',
    c.id, o.id, o.id,
    'scheduled', 'normal',
    '2026-04-01 10:30:00+00'::timestamptz,
    '2026-04-01 12:30:00+00'::timestamptz,
    '27 Clontarf Road, Dublin 3', 'D03 YK82', 120, '#3B82F6', 53.3638, -6.1902
FROM users o
JOIN customers c ON c.owner_id = o.id AND c.email = 'sarah.obrien@example.com'
WHERE o.email = 'owner@demo.com'
ON CONFLICT DO NOTHING;

-- Job 3: 13:30–15:30 - Afternoon
INSERT INTO jobs (title, description, customer_id, owner_id, created_by_id,
                  status, priority, start_time, end_time, location, eircode, estimated_duration, color, latitude, longitude)
SELECT
    'EV Charger Pre-Wire Inspection',
    'Survey garage electrical capacity, check earthing, and pre-wire 32A dedicated circuit for future EV charger.',
    c.id, o.id, o.id,
    'scheduled', 'normal',
    '2026-04-01 13:30:00+00'::timestamptz,
    '2026-04-01 15:30:00+00'::timestamptz,
    '5 Salthill Promenade, Galway', 'H91 FT56', 120, '#F59E0B', 53.2602, -9.0716
FROM users o
JOIN customers c ON c.owner_id = o.id AND c.email = 'tom.murphy@example.com'
WHERE o.email = 'owner@demo.com'
ON CONFLICT DO NOTHING;

-- Job 4: 16:00–17:30 - Late afternoon
INSERT INTO jobs (title, description, customer_id, owner_id, created_by_id,
                  status, priority, start_time, end_time, location, eircode, estimated_duration, color, latitude, longitude)
SELECT
    'Bathroom Extractor Fan Replacement',
    'Remove faulty extractor fan, install new inline unit with humidity sensor and timer.',
    c.id, o.id, o.id,
    'scheduled', 'low',
    '2026-04-01 16:00:00+00'::timestamptz,
    '2026-04-01 17:30:00+00'::timestamptz,
    '42 South Mall, Cork', 'T12 DH93', 90, '#10B981', 51.8969, -8.4713
FROM users o
JOIN customers c ON c.owner_id = o.id AND c.email = 'michael.byrne@example.com'
WHERE o.email = 'owner@demo.com'
ON CONFLICT DO NOTHING;

-- ──────────────────────────────────────────
-- Unscheduled (pending) jobs - appear in the job queue
-- ──────────────────────────────────────────

INSERT INTO jobs (title, description, customer_id, owner_id, created_by_id,
                  status, priority, location, eircode, estimated_duration)
SELECT
    'Follow-up Call - Kitchen Quote',
    'Call John Smith to finalise kitchen renovation quote and confirm start date.',
    c.id, o.id, o.id,
    'pending', 'high', '123 Main Street, Dublin 2', 'D02 XY45', 15
FROM users o
JOIN customers c ON c.owner_id = o.id AND c.email = 'john.smith@example.com'
WHERE o.email = 'owner@demo.com'
ON CONFLICT DO NOTHING;

INSERT INTO jobs (title, description, customer_id, owner_id, created_by_id,
                  status, priority, location, eircode, estimated_duration)
SELECT
    'Solar Panel Survey',
    'Rooftop survey for 12-panel solar PV installation. Check roof orientation and shading.',
    c.id, o.id, o.id,
    'pending', 'normal',
    '45 Grafton Street, Dublin 2', 'D02 VF25', 90
FROM users o
JOIN customers c ON c.owner_id = o.id AND c.email = 'sarah.obrien@example.com'
WHERE o.email = 'owner@demo.com'
ON CONFLICT DO NOTHING;

INSERT INTO jobs (title, description, owner_id, created_by_id,
                  status, priority, location, eircode, estimated_duration)
SELECT
    'New Client Consultation',
    'Initial meeting with prospective commercial client. Discuss maintenance contract options.',
    o.id, o.id,
    'pending', 'low', 'Office - 456 Business Park, Dublin', 'D04 AB12', 60
FROM users o
WHERE o.email = 'owner@demo.com'
ON CONFLICT DO NOTHING;

INSERT INTO jobs (title, description, customer_id, owner_id, created_by_id,
                  status, priority, location, eircode, estimated_duration)
SELECT
    'Fuse Board Upgrade',
    'Replace old fuse board with modern consumer unit. Full RECI certification required.',
    c.id, o.id, o.id,
    'pending', 'urgent',
    '8 Patrick Street, Cork', 'T12 W8KP', 480
FROM users o
JOIN customers c ON c.owner_id = o.id AND c.email = 'michael.byrne@example.com'
WHERE o.email = 'owner@demo.com'
ON CONFLICT DO NOTHING;


-- ──────────────────────────────────────────
-- Assign employees to jobs via junction table
-- ──────────────────────────────────────────
INSERT INTO job_employees (job_id, employee_id, owner_id)
SELECT j.id, emp.id, j.owner_id
FROM (VALUES
    ('Kitchen Renovation Consultation', 'employee@demo.com'),
    ('Bathroom Plumbing Repair', 'manager@demo.com'),
    ('Office Wiring Inspection', 'admin@demo.com'),
    ('Full House Rewiring - Phase 1', 'employee@demo.com'),
    ('Boiler Service', 'employee@demo.com'),
    ('Garden Lighting Installation', 'manager@demo.com'),
    ('Underfloor Heating Consultation', 'employee@demo.com'),
    ('Emergency Pipe Burst Repair', 'employee@demo.com'),
    ('Shop Fit-Out - Electrical', 'employee@demo.com'),
    ('Smart Home Setup', 'manager@demo.com'),
    ('Fire Alarm Certification', 'employee@demo.com'),
    ('Security Camera Installation', 'manager@demo.com'),
    ('Outdoor Socket Installation', 'admin@demo.com'),
    ('Full House Rewiring - Phase 2', 'employee@demo.com'),
    ('Emergency Boiler Breakdown', 'employee@demo.com'),
    ('Smoke Detector Battery Replacement', 'employee3@demo.com'),
    ('Dishwasher Electrical Connection', 'employee2@demo.com'),
    ('Heat Pump Annual Service', 'employee@demo.com'),
    ('Commercial Kitchen Extractor Wiring', 'employee@demo.com'),
    ('Data Cabling - Small Office', 'admin@demo.com'),
    ('Immersion Heater Replacement', 'employee2@demo.com'),
    ('Parking Lot Floodlight Repair', 'employee2@demo.com'),
    ('Apprentice Shadowing - Fire Alarm Cert', 'employee3@demo.com'),
    ('Thermostat Wiring Fault Diagnosis', 'employee@demo.com'),
    ('Commercial CCTV Maintenance', 'manager@demo.com'),
    ('Domestic Rewire Quotation', 'admin@demo.com'),
    ('Intercom System Upgrade', 'employee2@demo.com'),
    ('Air Conditioning Unit Service', 'employee@demo.com'),
    ('Server Room UPS Installation', 'manager@demo.com'),
    ('Cooker Circuit Installation', 'employee2@demo.com'),
    ('Emergency Power Outage Investigation', 'employee@demo.com'),
    ('Electric Gate Motor Repair', 'employee@demo.com'),
    ('Office LED Lighting Retrofit', 'admin@demo.com'),
    ('Earthing System Test', 'employee2@demo.com'),
    ('Apartment Block Rewire - Block A', 'employee@demo.com'),
    ('Cable Trunking Installation', 'admin@demo.com'),
    ('PAT Testing - Office Equipment', 'employee3@demo.com'),
    ('Doorbell Camera Installation', 'manager@demo.com'),
    ('Immersion Timer Replacement', 'employee2@demo.com'),
    ('Distribution Board Upgrade', 'employee2@demo.com'),
    ('Dimmer Switch Installation x6', 'manager@demo.com'),
    ('Garden Floodlight Setup', 'employee3@demo.com'),
    ('Sauna Electrical Hookup', 'employee@demo.com'),
    ('Electric Shower Installation', 'employee2@demo.com'),
    ('Shopping Centre Emergency Lighting Test', 'employee@demo.com'),
    ('Underfloor Heating Wiring', 'manager@demo.com'),
    ('Retail LED Lighting Upgrade', 'employee2@demo.com'),
    ('EV Charger Installation', 'employee2@demo.com'),
    ('Temporary Site Power Setup', 'employee3@demo.com'),
    ('BER Energy Assessment', 'admin@demo.com'),
    ('Industrial Motor Starter Replacement', 'employee@demo.com'),
    ('Smart Meter Upgrade', 'manager@demo.com'),
    ('Marquee Lighting Setup', 'employee3@demo.com'),
    ('Backup Generator Service', 'employee@demo.com'),
    ('Bathroom Heated Towel Rail Wiring', 'manager@demo.com'),
    ('Office Network Patch Panel', 'admin@demo.com'),
    ('Fire Safety Compliance Audit', 'employee2@demo.com'),
    ('Warehouse Full Electrical Audit', 'manager@demo.com'),
    ('Motion Sensor Light Installation', 'employee@demo.com'),
    ('Garage Consumer Unit Upgrade', 'employee3@demo.com'),
    ('New Build Pre-Wire - Phase 1', 'employee@demo.com'),
    ('CCTV Hard Drive Replacement', 'admin@demo.com'),
    ('Staircase LED Strip Lighting', 'manager@demo.com'),
    ('Emergency Light Battery Swap', 'employee2@demo.com'),
    ('Hot Tub Electrical Connection', 'employee2@demo.com'),
    ('Kitchen Socket Repositioning', 'manager@demo.com'),
    ('Weekend Emergency - Tripped RCD', 'employee@demo.com'),
    ('Annual Electrical Safety Cert', 'employee@demo.com'),
    ('Conference Room AV Wiring', 'admin@demo.com'),
    ('Outdoor Security Lighting', 'employee2@demo.com'),
    ('End-of-Quarter Equipment Inspection', 'manager@demo.com'),
    ('Electric Fence Controller Repair', 'employee@demo.com'),
    ('Month-End Timesheet & Invoice Review', 'admin@demo.com'),
    ('Commercial Fit-Out - Electrical Package', 'employee2@demo.com'),
    ('School Summer Works - Rewire Block B', 'employee3@demo.com'),
    ('Hotel Ballroom Lighting Refit', 'employee2@demo.com'),
    ('Annual PAT Testing - Full Site', 'employee3@demo.com'),
    ('Emergency Lighting Certification - All Buildings', 'manager@demo.com'),
    ('Smoke Alarm Replacement - Residential', 'employee@demo.com'),
    ('Outdoor Patio Lighting Setup', 'employee@demo.com'),
    ('EV Charger Pre-Wire Inspection', 'employee@demo.com'),
    ('Bathroom Extractor Fan Replacement', 'employee@demo.com')
) AS mapping(job_title, emp_email)
JOIN users o ON o.email = 'owner@demo.com'
JOIN jobs j ON j.title = mapping.job_title AND j.owner_id = o.id
JOIN employees emp ON emp.owner_id = o.id
JOIN users eu ON eu.id = emp.user_id AND eu.email = mapping.emp_email
ON CONFLICT ON CONSTRAINT unique_job_employee_assignment DO NOTHING;

-- ==========================================================================
-- DEFAULT ROLE-BASED PERMISSIONS
-- ==========================================================================
-- Manager permissions
INSERT INTO user_permissions (owner_id, user_id, permission, granted)
SELECT o.id, u.id, perm.name, TRUE
FROM users o, users u,
     (VALUES ('company.view'),('employees.create'),('employees.edit'),
             ('customers.create'),('customers.edit'),
             ('jobs.create'),('jobs.edit'),('jobs.assign'),
             ('jobs.schedule'),('jobs.update_status'),
             ('notes.create'),('notes.edit')) AS perm(name)
WHERE o.email = 'owner@demo.com' AND u.email = 'manager@demo.com'
ON CONFLICT ON CONSTRAINT uq_user_permissions_owner_user_perm DO NOTHING;

-- Employee permissions
INSERT INTO user_permissions (owner_id, user_id, permission, granted)
SELECT o.id, u.id, perm.name, TRUE
FROM users o, users u,
     (VALUES ('company.view'),('customers.create'),('customers.edit'),
             ('jobs.create'),('jobs.edit'),('jobs.update_status'),
             ('notes.create'),('notes.edit')) AS perm(name)
WHERE o.email = 'owner@demo.com' AND u.email = 'employee@demo.com'
ON CONFLICT ON CONSTRAINT uq_user_permissions_owner_user_perm DO NOTHING;

-- Viewer permissions
INSERT INTO user_permissions (owner_id, user_id, permission, granted)
SELECT o.id, u.id, perm.name, TRUE
FROM users o, users u,
     (VALUES ('company.view')) AS perm(name)
WHERE o.email = 'owner@demo.com' AND u.email = 'viewer@demo.com'
ON CONFLICT ON CONSTRAINT uq_user_permissions_owner_user_perm DO NOTHING;

-- ============================================
-- Backfill missing eircodes on all job locations
-- ============================================
UPDATE jobs SET eircode = 'D02 XY45' WHERE location = '123 Main Street, Dublin 2' AND eircode IS NULL;
UPDATE jobs SET eircode = 'D02 VF25' WHERE location = '45 Grafton Street, Dublin 2' AND eircode IS NULL;
UPDATE jobs SET eircode = 'D02 HK56' WHERE location = '22 Grafton Street, Dublin 2' AND eircode IS NULL;
UPDATE jobs SET eircode = 'T12 W8KP' WHERE location = '8 Patrick Street, Cork' AND eircode IS NULL;
UPDATE jobs SET eircode = 'V94 T28R' WHERE location = '12 O''Connell Street, Limerick' AND eircode IS NULL;
UPDATE jobs SET eircode = 'H91 KT23' WHERE location = '67 Eyre Square, Galway' AND eircode IS NULL;
UPDATE jobs SET eircode = 'H91 RD45' WHERE location = '5 Eyre Square, Galway' AND eircode IS NULL;
UPDATE jobs SET eircode = 'X91 PK12' WHERE location = '33 The Quay, Waterford' AND eircode IS NULL;
UPDATE jobs SET eircode = 'A91 X2T7' WHERE location = '15 Seatown Road, Dundalk' AND eircode IS NULL;
UPDATE jobs SET eircode = 'D04 AB12' WHERE location = 'Office - 456 Business Park, Dublin' AND eircode IS NULL;

-- ============================================
-- Geocode job locations (latitude/longitude for map view)
-- ============================================
UPDATE jobs SET latitude = 53.3420, longitude = -6.2598 WHERE location = '123 Main Street, Dublin 2' AND latitude IS NULL;
UPDATE jobs SET latitude = 53.3418, longitude = -6.2593 WHERE location = '45 Grafton Street, Dublin 2' AND latitude IS NULL;
UPDATE jobs SET latitude = 53.3405, longitude = -6.2606 WHERE location = '22 Grafton Street, Dublin 2' AND latitude IS NULL;
UPDATE jobs SET latitude = 51.8985, longitude = -8.4756 WHERE location = '8 Patrick Street, Cork' AND latitude IS NULL;
UPDATE jobs SET latitude = 52.6638, longitude = -8.6267 WHERE location = '12 O''Connell Street, Limerick' AND latitude IS NULL;
UPDATE jobs SET latitude = 53.2743, longitude = -9.0514 WHERE location = '5 Eyre Square, Galway' AND latitude IS NULL;
UPDATE jobs SET latitude = 53.2750, longitude = -9.0490 WHERE location = '67 Eyre Square, Galway' AND latitude IS NULL;
UPDATE jobs SET latitude = 52.2593, longitude = -7.1101 WHERE location = '33 The Quay, Waterford' AND latitude IS NULL;
UPDATE jobs SET latitude = 53.9967, longitude = -6.4033 WHERE location = '15 Seatown Road, Dundalk' AND latitude IS NULL;
UPDATE jobs SET latitude = 53.3558, longitude = -6.2420 WHERE location = 'Office - 456 Business Park, Dublin' AND latitude IS NULL;

-- ============================================
-- Diversify job locations: ensure no two jobs share the same address/eircode
-- Keeps one job per original customer address; reassigns the rest to unique
-- Irish locations so every job has a distinct map pin.
-- ============================================
WITH address_pool(seq, addr, eircode, lat, lng) AS (VALUES
    -- Dublin (30)
    (1,  '10 Pearse Street, Dublin 2',          'D02 TN83', 53.3438, -6.2490),
    (2,  '27 Baggot Street Lower, Dublin 2',    'D02 KX74', 53.3380, -6.2482),
    (3,  '14 Harcourt Street, Dublin 2',         'D02 PW29', 53.3348, -6.2620),
    (4,  '5 Merrion Square, Dublin 2',           'D02 AF81', 53.3393, -6.2480),
    (5,  '38 Camden Street, Dublin 2',           'D02 EK47', 53.3337, -6.2645),
    (6,  '19 Dawson Street, Dublin 2',           'D02 HT63', 53.3405, -6.2577),
    (7,  '3 Aungier Street, Dublin 2',           'D02 NP52', 53.3377, -6.2662),
    (8,  '42 Wexford Street, Dublin 2',          'D02 RC95', 53.3345, -6.2674),
    (9,  '11 South William Street, Dublin 2',    'D02 WL38', 53.3414, -6.2622),
    (10, '29 Drury Street, Dublin 2',            'D02 FA67', 53.3424, -6.2637),
    (11, '7 Ranelagh Road, Dublin 6',            'D06 YH93', 53.3268, -6.2620),
    (12, '15 Rathmines Road, Dublin 6',          'D06 BT15', 53.3235, -6.2635),
    (13, '21 Donnybrook Road, Dublin 4',         'D04 PK82', 53.3190, -6.2350),
    (14, '55 Clanbrassil Street, Dublin 8',      'D08 XR47', 53.3360, -6.2730),
    (15, '33 Thomas Street, Dublin 8',           'D08 HW63', 53.3432, -6.2835),
    (16, '9 Phibsborough Road, Dublin 7',        'D07 TN52', 53.3575, -6.2720),
    (17, '40 Dorset Street, Dublin 1',           'D01 YK38', 53.3565, -6.2645),
    (18, '17 Amiens Street, Dublin 1',           'D01 VR84', 53.3510, -6.2485),
    (19, '6 Capel Street, Dublin 1',             'D01 CW72', 53.3482, -6.2715),
    (20, '24 Talbot Street, Dublin 1',           'D01 NK59', 53.3505, -6.2565),
    (21, '8 Ballsbridge Terrace, Dublin 4',      'D04 FE23', 53.3280, -6.2290),
    (22, '31 Sandymount Road, Dublin 4',         'D04 WR91', 53.3285, -6.2160),
    (23, '12 Stillorgan Road, Dublin 4',         'D04 JH67', 53.3120, -6.2260),
    (24, '45 Clontarf Road, Dublin 3',           'D03 PN48', 53.3630, -6.2140),
    (25, '18 Drumcondra Road, Dublin 9',         'D09 XH35', 53.3680, -6.2590),
    (26, '52 Howth Road, Dublin 5',              'D05 BK72', 53.3670, -6.1860),
    (27, '2 Glasnevin Avenue, Dublin 11',        'D11 TW94', 53.3705, -6.2710),
    (28, '36 Terenure Road, Dublin 6W',          'D6W RK29', 53.3115, -6.2800),
    (29, '23 Harolds Cross Road, Dublin 6W',     'D6W LN46', 53.3275, -6.2750),
    (30, '14 Rathgar Road, Dublin 6',            'D06 FP83', 53.3180, -6.2700),
    -- Cork (15)
    (31, '22 South Mall, Cork',                  'T12 FK83', 51.8975, -8.4700),
    (32, '15 Oliver Plunkett Street, Cork',      'T12 RN47', 51.8982, -8.4730),
    (33, '9 Washington Street, Cork',            'T12 HE52', 51.8967, -8.4805),
    (34, '37 MacCurtain Street, Cork',           'T23 AK68', 51.9010, -8.4735),
    (35, '4 Grand Parade, Cork',                 'T12 WT91', 51.8970, -8.4760),
    (36, '28 Bandon Road, Cork',                 'T12 XV34', 51.8895, -8.4855),
    (37, '11 Douglas Street, Cork',              'T12 LC78', 51.8925, -8.4795),
    (38, '20 Barrack Street, Cork',              'T12 PE49', 51.8945, -8.4825),
    (39, '6 Summerhill North, Cork',             'T23 DN63', 51.9025, -8.4760),
    (40, '31 Blarney Street, Cork',              'T23 YF87', 51.9005, -8.4840),
    (41, '45 Blackpool Road, Cork',              'T23 KR54', 51.9070, -8.4775),
    (42, '13 Ballincollig Main Street, Cork',    'P31 AX28', 51.8880, -8.5895),
    (43, '8 Midleton Main Street, Cork',         'P25 NK67', 51.9145, -8.1715),
    (44, '17 Cobh Promenade, Cork',              'P24 RW43', 51.8505, -8.2940),
    (45, '25 Mallow Main Street, Cork',          'P51 TH82', 52.1345, -8.6370),
    -- Galway (10)
    (46, '14 Shop Street, Galway',               'H91 PN47', 53.2738, -9.0530),
    (47, '8 Quay Street, Galway',                'H91 XE83', 53.2710, -9.0530),
    (48, '22 Salthill Promenade, Galway',        'H91 FK56', 53.2570, -9.0750),
    (49, '3 Dominick Street, Galway',            'H91 WN29', 53.2752, -9.0567),
    (50, '31 Prospect Hill, Galway',             'H91 DC68', 53.2760, -9.0550),
    (51, '16 Fr Griffin Road, Galway',           'H91 LT42', 53.2650, -9.0600),
    (52, '9 Bohermore Road, Galway',             'H91 YK75', 53.2790, -9.0440),
    (53, '44 Headford Road, Galway',             'H91 AW14', 53.2810, -9.0560),
    (54, '7 Knocknacarra Road, Galway',          'H91 PM83', 53.2720, -9.0910),
    (55, '20 Oranmore Main Street, Galway',      'H91 TX37', 53.2675, -8.9305),
    -- Limerick (10)
    (56, '7 William Street, Limerick',           'V94 WK58', 52.6630, -8.6235),
    (57, '18 Catherine Street, Limerick',        'V94 XN73', 52.6620, -8.6260),
    (58, '25 Henry Street, Limerick',            'V94 HK42', 52.6640, -8.6220),
    (59, '11 Roches Street, Limerick',           'V94 PD87', 52.6615, -8.6270),
    (60, '33 Mulgrave Street, Limerick',         'V94 TR94', 52.6605, -8.6175),
    (61, '6 Parnell Street, Limerick',           'V94 BN35', 52.6648, -8.6245),
    (62, '14 Denmark Street, Limerick',          'V94 KC61', 52.6655, -8.6218),
    (63, '40 Ennis Road, Limerick',              'V94 FW28', 52.6715, -8.6410),
    (64, '8 Childers Road, Limerick',            'V94 AH53', 52.6510, -8.6355),
    (65, '22 Dooradoyle Road, Limerick',         'V94 YN68', 52.6415, -8.6560),
    -- Waterford (10)
    (66, '15 Barronstrand Street, Waterford',    'X91 HE45', 52.2600, -7.1090),
    (67, '9 John Street, Waterford',             'X91 TK27', 52.2585, -7.1060),
    (68, '21 Broad Street, Waterford',           'X91 WN84', 52.2608, -7.1065),
    (69, '5 Michael Street, Waterford',          'X91 PA63', 52.2595, -7.1040),
    (70, '30 Manor Street, Waterford',           'X91 KR57', 52.2575, -7.1115),
    (71, '12 Peter Street, Waterford',           'X91 DF48', 52.2580, -7.1085),
    (72, '7 Parnell Street, Waterford',          'X91 NC92', 52.2610, -7.1105),
    (73, '18 Patrick Street, Waterford',         'X91 BW36', 52.2590, -7.1050),
    (74, '40 Cork Road, Waterford',              'X91 FH71', 52.2520, -7.1185),
    (75, '25 Tramore Road, Waterford',           'X91 LK89', 52.2465, -7.1210)
),
jobs_to_move AS (
    SELECT id, ROW_NUMBER() OVER (ORDER BY id) as seq
    FROM (
        SELECT id,
               ROW_NUMBER() OVER (PARTITION BY location ORDER BY id) as rn
        FROM jobs
        WHERE location IS NOT NULL
    ) sub
    WHERE rn > 1
)
UPDATE jobs
SET location  = ap.addr,
    eircode   = ap.eircode,
    latitude  = ap.lat,
    longitude = ap.lng
FROM jobs_to_move jtm
JOIN address_pool ap ON ap.seq = jtm.seq
WHERE jobs.id = jtm.id;

DO $$ BEGIN RAISE NOTICE 'Demo seed data loaded successfully!'; END $$;
