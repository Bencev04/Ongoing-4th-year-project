# ============================================================================
# Bootstrap - Run ONCE manually to create the S3 + DynamoDB Terraform backend
# ============================================================================
#
# WHY THIS EXISTS:
#   Terraform needs a remote backend to store its state file. But we can't use
#   Terraform to create the backend that Terraform itself needs - chicken-and-egg.
#   So this small config is run manually ONCE from your local machine to create
#   the S3 bucket and DynamoDB table. After that, everything else uses remote state.
#
# USAGE:
#   cd bootstrap
#   terraform init
#   terraform apply
#
# YOU ONLY RUN THIS ONCE. If the bucket already exists, this is a no-op.
# ============================================================================

# Require Terraform 1.9+ and the AWS provider
terraform {
  required_version = ">= 1.9"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

# Uses the default AWS credentials from your local `aws configure` or env vars
provider "aws" {
  region = var.aws_region
}

# =============================================================================
# S3 Bucket - Stores the Terraform state file (terraform.tfstate)
# =============================================================================
# The state file tracks every AWS resource Terraform manages, so Terraform knows
# what exists and what needs to change on the next `terraform apply`.
# We store it in S3 (not locally) so that:
#   - Multiple people / CI pipelines can share the same state
#   - The state is backed up (S3 versioning) and encrypted at rest
#   - We can lock it during applies to prevent corruption
# =============================================================================

resource "aws_s3_bucket" "terraform_state" {
  bucket = var.state_bucket_name # Must be globally unique across all of AWS

  lifecycle {
    prevent_destroy = true # Safety: Terraform will refuse to delete this bucket
  }

  tags = {
    Project   = var.project_name
    ManagedBy = "terraform-bootstrap"
  }
}

# Enable versioning so we can roll back to a previous state if something goes wrong
resource "aws_s3_bucket_versioning" "terraform_state" {
  bucket = aws_s3_bucket.terraform_state.id

  versioning_configuration {
    status = "Enabled"
  }
}

# Encrypt the state file at rest - it contains sensitive info like RDS passwords
resource "aws_s3_bucket_server_side_encryption_configuration" "terraform_state" {
  bucket = aws_s3_bucket.terraform_state.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256" # AWS-managed encryption key (SSE-S3)
    }
  }
}

# Block ALL public access - this bucket should never be publicly readable
resource "aws_s3_bucket_public_access_block" "terraform_state" {
  bucket = aws_s3_bucket.terraform_state.id

  block_public_acls       = true # Reject any ACL that grants public access
  block_public_policy     = true # Reject any bucket policy that grants public access
  ignore_public_acls      = true # Ignore any existing public ACLs
  restrict_public_buckets = true # Restrict cross-account access
}

# =============================================================================
# DynamoDB Table - Provides state locking during `terraform apply`
# =============================================================================
# When someone runs `terraform apply`, Terraform writes a lock to this table.
# If a second person tries to apply at the same time, they'll get a lock error
# instead of corrupting the state file. Essential for CI/CD pipelines.
# PAY_PER_REQUEST billing means we only pay when the lock is used (fractions of a cent).
# =============================================================================

resource "aws_dynamodb_table" "terraform_locks" {
  name         = var.lock_table_name
  billing_mode = "PAY_PER_REQUEST" # No provisioned capacity needed - usage is tiny
  hash_key     = "LockID"          # Terraform uses this key name by convention

  attribute {
    name = "LockID"
    type = "S" # String type
  }

  tags = {
    Project   = var.project_name
    ManagedBy = "terraform-bootstrap"
  }
}
