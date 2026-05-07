"""
One-time script to fix seed-demo-data.sql after migration 0003
removed jobs.assigned_employee_id in favour of the job_employees junction table.

Steps:
1. Collect (job_title, employee_email) mappings from existing INSERT blocks.
2. Remove ', assigned_employee_id' from column lists.
3. Remove 'emp.id' from SELECT value lists.
4. Remove now-unnecessary employee JOINs.
5. Add DELETE FROM job_employees in cleanup section.
6. Add bulk INSERT INTO job_employees at the end.
"""

import re
from pathlib import Path

SEED_FILE = Path(__file__).parent / "seed-demo-data.sql"

content = SEED_FILE.read_text(encoding="utf-8")

# ── Step 1: Collect (title, employee_email) mappings ────────────────────────
# Split on INSERT INTO jobs to isolate each INSERT block.
blocks = content.split("INSERT INTO jobs")
mappings: list[tuple[str, str]] = []

for block in blocks[1:]:  # skip preamble
    if "assigned_employee_id" not in block:
        continue
    # Title is the first single-quoted string after SELECT
    title_m = re.search(r"SELECT\s*\n\s+'((?:[^']|'')*)'", block)
    if not title_m:
        continue
    title = title_m.group(1)  # keeps SQL escaping like O''Brien
    # Employee email
    email_m = re.search(r"eu\.email\s*=\s*'([^']+)'", block)
    if not email_m:
        continue
    mappings.append((title, email_m.group(1)))

print(f"Collected {len(mappings)} job → employee mappings")

# ── Step 2: Remove ', assigned_employee_id' from column lists ───────────────
content = content.replace(", assigned_employee_id", "")

# ── Step 3: Remove 'emp.id' from SELECT value lists ────────────────────────
# Pattern A: "c.id, emp.id, o.id, o.id," (with customer_id)
content = content.replace("c.id, emp.id, o.id, o.id,", "c.id, o.id, o.id,")
# Pattern B: "emp.id, o.id, o.id," at start of value line (no customer_id)
content = re.sub(r"(\n\s+)emp\.id, o\.id, o\.id,", r"\1o.id, o.id,", content)

# ── Step 4: Remove employee JOINs that were only for assignment ─────────────
content = re.sub(
    r"\nJOIN employees emp ON emp\.owner_id = o\.id\s*\n",
    "\n",
    content,
)
content = re.sub(
    r"\nJOIN users eu ON eu\.id = emp\.user_id AND eu\.email = '[^']+'\s*\n",
    "\n",
    content,
)

# ── Step 5: Add DELETE FROM job_employees in cleanup section ────────────────
old_cleanup = (
    "DELETE FROM job_history WHERE job_id IN (\n"
    "    SELECT id FROM jobs WHERE owner_id = "
    "(SELECT id FROM users WHERE email = 'owner@demo.com')\n"
    ");"
)
new_cleanup = (
    "DELETE FROM job_employees WHERE job_id IN (\n"
    "    SELECT id FROM jobs WHERE owner_id = "
    "(SELECT id FROM users WHERE email = 'owner@demo.com')\n"
    ");\n" + old_cleanup
)
content = content.replace(old_cleanup, new_cleanup, 1)

# ── Step 6: Build bulk INSERT INTO job_employees ────────────────────────────
values_lines = [f"    ('{t}', '{e}')" for t, e in mappings]
values_str = ",\n".join(values_lines)

bulk_insert = f"""
-- ──────────────────────────────────────────
-- Assign employees to jobs via junction table
-- ──────────────────────────────────────────
INSERT INTO job_employees (job_id, employee_id, owner_id)
SELECT j.id, emp.id, j.owner_id
FROM (VALUES
{values_str}
) AS mapping(job_title, emp_email)
JOIN users o ON o.email = 'owner@demo.com'
JOIN jobs j ON j.title = mapping.job_title AND j.owner_id = o.id
JOIN employees emp ON emp.owner_id = o.id
JOIN users eu ON eu.id = emp.user_id AND eu.email = mapping.emp_email
ON CONFLICT ON CONSTRAINT unique_job_employee_assignment DO NOTHING;

"""

# Insert before the permissions section
marker = (
    "-- ==========================================================================\n"
    "-- DEFAULT ROLE-BASED PERMISSIONS"
)
if marker not in content:
    raise RuntimeError("Could not find permissions section marker")
content = content.replace(marker, bulk_insert + marker)

# ── Write ───────────────────────────────────────────────────────────────────
SEED_FILE.write_text(content, encoding="utf-8")
print("seed-demo-data.sql updated successfully!")
for t, e in mappings:
    print(f"  {t} → {e}")
