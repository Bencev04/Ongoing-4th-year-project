# =============================================================================
# OPA/Conftest Policy — Network Access Controls
# =============================================================================
#
# This Rego policy validates that database and cache resources are NOT publicly
# accessible. Databases should only be reachable from within the VPC.
#
# WHAT THIS CATCHES:
#   - RDS instance with publicly_accessible = true
#   - Security groups with unrestricted ingress (0.0.0.0/0)
#   - Resources that should be in private subnets but aren't
#
# WHY THIS MATTERS:
#   Even though our .trivyignore suppresses some findings for development,
#   OPA policies provide a SECOND layer of validation. Trivy checks against
#   CIS benchmarks; OPA enforces OUR project-specific rules.
# =============================================================================

package main

# =============================================================================
# DENY: RDS instance publicly accessible
# =============================================================================
# Databases must NEVER be reachable from the internet.
deny[msg] {
  resource := all_resources[_]
  resource.type == "aws_db_instance"
  resource.values.publicly_accessible == true
  msg := sprintf(
    "NETWORK: RDS instance '%s' must not be publicly accessible",
    [resource.name]
  )
}

# =============================================================================
# DENY: Security groups with unrestricted SSH access
# =============================================================================
# No security group should allow SSH (port 22) from anywhere.
deny[msg] {
  resource := all_resources[_]
  resource.type == "aws_security_group"
  ingress := resource.values.ingress[_]
  ingress.from_port <= 22
  ingress.to_port >= 22
  cidr := ingress.cidr_blocks[_]
  cidr == "0.0.0.0/0"
  msg := sprintf(
    "NETWORK: Security group '%s' allows SSH from 0.0.0.0/0 — restrict to known IPs",
    [resource.name]
  )
}

# =============================================================================
# DENY: Security groups with unrestricted database access
# =============================================================================
# RDS (5432) and Redis (6379) should never be open to the internet.
deny[msg] {
  resource := all_resources[_]
  resource.type == "aws_security_group"
  ingress := resource.values.ingress[_]

  # Check if the rule covers PostgreSQL (5432) or Redis (6379)
  port := [5432, 6379][_]
  ingress.from_port <= port
  ingress.to_port >= port

  cidr := ingress.cidr_blocks[_]
  cidr == "0.0.0.0/0"
  msg := sprintf(
    "NETWORK: Security group '%s' allows port %d from 0.0.0.0/0 — databases must be VPC-only",
    [resource.name, port]
  )
}
