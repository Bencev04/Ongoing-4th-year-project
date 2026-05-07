# =============================================================================
# Provider Configuration - Which versions of Terraform and providers we need
# =============================================================================
#
# WHY PIN VERSIONS?
#   Terraform and its providers release new versions regularly. Pinning ensures:
#   - Everyone on the team gets the same behavior
#   - CI/CD pipelines produce consistent results
#   - We don't accidentally get breaking changes
#
# VERSION CONSTRAINTS EXPLAINED:
#   ">= 1.5"   = Terraform 1.5 or newer (any minor/patch)
#   "~> 5.0"   = AWS provider 5.x (any 5.x.x, but NOT 6.0)
#   "~> 4.0"   = TLS provider 4.x (any 4.x.x, but NOT 5.0)
# =============================================================================

terraform {
  required_version = ">= 1.9" # We use features introduced in Terraform 1.5+

  required_providers {
    # AWS provider - creates all AWS resources (VPC, EKS, RDS, ElastiCache, etc.)
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    # TLS provider - used by the EKS module to fetch the OIDC TLS certificate
    # (needed for IRSA - IAM Roles for Service Accounts)
    tls = {
      source  = "hashicorp/tls"
      version = "~> 4.0"
    }
  }
}

# =============================================================================
# AWS Provider - Region and default tags
# =============================================================================
# default_tags are applied to EVERY resource automatically, so we don't have to
# repeat them in each module. These tags appear in the AWS console and help with
# cost tracking and resource identification.

provider "aws" {
  region = var.aws_region # Default: eu-west-1 (Ireland)

  default_tags {
    tags = {
      Project    = var.project_name       # "yr4-project"
      ManagedBy  = "terraform"            # So we know not to edit manually!
      Repository = "yr4-projectinfrarepo" # Which repo manages this resource
    }
  }
}
