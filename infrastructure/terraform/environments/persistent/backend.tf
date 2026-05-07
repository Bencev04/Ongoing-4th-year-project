# =============================================================================
# Backend - Persistent layer state (always-on resources)
# =============================================================================
# Secrets Manager secrets that must exist BEFORE any cluster is created.
# Completely independent from staging/production infrastructure.
#
# STATE FILE PATH:
#   s3://yr4-project-tf-state/persistent/terraform.tfstate
# =============================================================================

terraform {
  backend "s3" {
    bucket         = "yr4-project-tf-state"
    key            = "persistent/terraform.tfstate"
    region         = "eu-west-1"
    dynamodb_table = "yr4-project-terraform-locks"
    encrypt        = true
  }
}
