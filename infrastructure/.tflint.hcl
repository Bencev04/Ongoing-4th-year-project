# =============================================================================
# TFLint Configuration — Terraform Linter
# =============================================================================
#
# TFLint catches errors that `terraform validate` misses:
#   - Invalid AWS instance types (e.g. "db.t3.mikro" typo)
#   - Deprecated resource attributes
#   - Naming convention violations
#   - AWS-specific best practices (unused variables, missing tags, etc.)
#
# HOW IT WORKS:
#   The "aws" plugin downloads AWS-specific rules from the TFLint ruleset.
#   TFLint reads your .tf files and checks them against these rules WITHOUT
#   making any AWS API calls — it's purely static analysis.
#
# RUN LOCALLY:
#   tflint --init       # Download the AWS plugin
#   tflint --recursive  # Lint all modules
# =============================================================================

# --- AWS Plugin --------------------------------------------------------------
# This plugin adds ~300 AWS-specific rules covering:
#   - Valid instance types for EC2, RDS, ElastiCache, etc.
#   - Valid engine versions for RDS and ElastiCache
#   - Deprecated resource attributes
#   - Region-specific availability checks
plugin "aws" {
  enabled = true
  version = "0.36.0"
  source  = "github.com/terraform-linters/tflint-ruleset-aws"
}

# --- General Rules -----------------------------------------------------------

# Enforce standard Terraform naming conventions
# (snake_case for resources, variables, outputs, etc.)
rule "terraform_naming_convention" {
  enabled = true
}

# Warn about variables declared but never used in the module
rule "terraform_unused_declarations" {
  enabled = true
}

# Require all variables and outputs to have a description
# (good practice and we already do this, so this enforces it stays that way)
rule "terraform_documented_variables" {
  enabled = true
}

rule "terraform_documented_outputs" {
  enabled = true
}

# Enforce consistent Terraform formatting (complements terraform fmt)
rule "terraform_standard_module_structure" {
  enabled = true
}
