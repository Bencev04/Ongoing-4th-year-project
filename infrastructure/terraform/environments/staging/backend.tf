# =============================================================================
# Backend - Staging environment state (separate from production)
# =============================================================================
# Each environment gets its own state file in S3 so they can be managed
# independently. Staging can be created/destroyed without affecting prod.
#
# STATE FILE PATH:
#   s3://yr4-project-tf-state/staging/terraform.tfstate
# =============================================================================

terraform {
  backend "s3" {
    bucket         = "yr4-project-tf-state"
    key            = "staging/terraform.tfstate"
    region         = "eu-west-1"
    dynamodb_table = "yr4-project-terraform-locks"
    encrypt        = true
  }
}
