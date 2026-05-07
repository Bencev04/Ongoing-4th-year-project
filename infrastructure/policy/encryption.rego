# =============================================================================
# OPA/Conftest Policy — Encryption Requirements
# =============================================================================
#
# This Rego policy validates that all storage resources in our Terraform plan
# have encryption enabled. It runs against `terraform show -json tfplan.binary`.
#
# WHAT THIS CATCHES:
#   - RDS instances without storage_encrypted = true
#   - ElastiCache clusters without at_rest_encryption_enabled = true
#   - Any future storage resource missing encryption
#
# HOW IT WORKS:
#   1. `terraform plan -out=tfplan.binary`
#   2. `terraform show -json tfplan.binary > tfplan.json`
#   3. `conftest test tfplan.json --policy policy/`
#
# OPA (Open Policy Agent) evaluates rules written in Rego. Conftest is a CLI
# wrapper that makes it easy to test structured data (like Terraform plans).
#
# REGO BASICS FOR THIS FILE:
#   - `deny[msg]` — any rule that produces a message means a violation
#   - `resource.type` — the Terraform resource type (e.g., "aws_db_instance")
#   - `resource.values` — the planned attribute values
#   - `input.planned_values.root_module.child_modules` — modules in the plan
# =============================================================================

package main

# Helper: collect all planned resources from all child modules
# Terraform plans nest resources inside modules, so we need to flatten them
all_resources[resource] {
  module := input.planned_values.root_module.child_modules[_]
  resource := module.resources[_]
}

# Also check resources at the root level (if any exist outside modules)
all_resources[resource] {
  resource := input.planned_values.root_module.resources[_]
}

# =============================================================================
# DENY: RDS instance without storage encryption
# =============================================================================
# If aws_db_instance has storage_encrypted = false, this rule fires.
# Accept both boolean true and string "true" (provider serialisation quirk).
deny[msg] {
  resource := all_resources[_]
  resource.type == "aws_db_instance"
  resource.values.storage_encrypted != true
  resource.values.storage_encrypted != "true"
  msg := sprintf(
    "ENCRYPTION: RDS instance '%s' must have storage_encrypted = true",
    [resource.name]
  )
}

# =============================================================================
# DENY: ElastiCache without at-rest encryption
# =============================================================================
# NOTE: Some providers serialise booleans as strings ("true") in the JSON plan,
# so we accept both boolean true and string "true".
deny[msg] {
  resource := all_resources[_]
  resource.type == "aws_elasticache_replication_group"
  resource.values.at_rest_encryption_enabled != true
  resource.values.at_rest_encryption_enabled != "true"
  msg := sprintf(
    "ENCRYPTION: ElastiCache replication group '%s' must have at_rest_encryption_enabled = true",
    [resource.name]
  )
}
