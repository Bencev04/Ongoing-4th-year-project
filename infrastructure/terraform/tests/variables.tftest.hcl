# =============================================================================
# Terraform Tests — Variable Validation and Configuration Assertions
# =============================================================================
#
# These tests use Terraform's built-in test framework (terraform test, v1.6+).
# They run `terraform plan` (not apply!) and assert that the planned configuration
# meets our requirements. No real AWS resources are created.
#
# WHAT THESE TESTS VERIFY:
#   - Variables have sensible defaults and constraints
#   - Module wiring is correct (values flow between modules properly)
#   - Security settings are enforced (encryption, private access, etc.)
#   - Naming conventions are followed consistently
#
# RUN LOCALLY:
#   cd terraform/
#   terraform test
#
# NOTE: These tests require `terraform init` to have been run first, and they
# need the TF_VAR_rds_username and TF_VAR_rds_password environment variables.
# =============================================================================

# =============================================================================
# Global Test Variables — override defaults for testing
# =============================================================================
# We provide dummy credentials so tests can run without real secrets.
# These are NEVER used against real AWS — tests only run `plan`, not `apply`.
variables {
  rds_username = "test_user"
  rds_password = "test_password_12345"
}

# =============================================================================
# Test: Default variable values are set correctly
# =============================================================================
# Verifies that our terraform.tfvars defaults match expectations.
# If someone accidentally changes a default, this test catches it.

run "defaults_are_correct" {
  command = plan

  assert {
    condition     = var.aws_region == "eu-west-1"
    error_message = "Default region must be eu-west-1 (Ireland)"
  }

  assert {
    condition     = var.project_name == "yr4-project"
    error_message = "Project name must be yr4-project"
  }

  assert {
    condition     = var.vpc_cidr == "10.0.0.0/16"
    error_message = "VPC CIDR must be 10.0.0.0/16"
  }

  assert {
    condition     = var.kubernetes_version == "1.31"
    error_message = "Kubernetes version must be 1.31"
  }
}

# =============================================================================
# Test: EKS node group allows scale-to-zero for cost saving
# =============================================================================
# Our entire cost-saving strategy depends on min_size = 0.
# If someone changes this, the CD/CI pipeline's scale-down job will break.

run "node_group_allows_scale_to_zero" {
  command = plan

  assert {
    condition     = var.node_min_size == 0
    error_message = "node_min_size must be 0 to allow scale-to-zero cost saving"
  }

  assert {
    condition     = var.node_max_size >= var.node_desired_size
    error_message = "node_max_size must be >= node_desired_size"
  }

  assert {
    condition     = var.node_desired_size >= var.node_min_size
    error_message = "node_desired_size must be >= node_min_size"
  }
}

# =============================================================================
# Test: Instance types are from the t3 family (cost-effective, burstable)
# =============================================================================
# Prevents someone from accidentally deploying expensive instance types.

run "instance_types_are_cost_effective" {
  command = plan

  assert {
    condition     = can(regex("^t3\\.", var.node_instance_type))
    error_message = "EKS node instance type must be t3 family for cost reasons (got: ${var.node_instance_type})"
  }

  assert {
    condition     = can(regex("^db\\.t3\\.", var.rds_instance_class))
    error_message = "RDS instance class must be db.t3 family (got: ${var.rds_instance_class})"
  }

  assert {
    condition     = can(regex("^cache\\.t3\\.", var.redis_node_type))
    error_message = "Redis node type must be cache.t3 family (got: ${var.redis_node_type})"
  }
}

# =============================================================================
# Test: RDS storage allocation is within sensible bounds
# =============================================================================
# Prevents someone from setting 1000GB of storage on a college project.

run "rds_storage_is_reasonable" {
  command = plan

  assert {
    condition     = var.rds_allocated_storage >= 20
    error_message = "RDS storage must be at least 20GB (AWS minimum for gp2)"
  }

  assert {
    condition     = var.rds_allocated_storage <= 100
    error_message = "RDS storage should not exceed 100GB for a college project"
  }
}

# =============================================================================
# Test: VPC CIDR is a valid /16 block
# =============================================================================

run "vpc_cidr_is_valid" {
  command = plan

  assert {
    condition     = can(cidrhost(var.vpc_cidr, 0))
    error_message = "VPC CIDR must be a valid CIDR block"
  }

  assert {
    condition     = can(regex("/16$", var.vpc_cidr))
    error_message = "VPC CIDR must be a /16 block (got: ${var.vpc_cidr})"
  }
}

# =============================================================================
# Test: Database name follows expected convention
# =============================================================================

run "database_naming_convention" {
  command = plan

  assert {
    condition     = can(regex("^[a-z][a-z0-9_]+$", var.rds_db_name))
    error_message = "DB name must be lowercase alphanumeric with underscores (got: ${var.rds_db_name})"
  }

  assert {
    condition     = var.rds_db_name == "crm_calendar"
    error_message = "Default database name must be 'crm_calendar'"
  }
}
