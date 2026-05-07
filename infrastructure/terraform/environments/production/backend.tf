# =============================================================================
# Backend - Production environment state (separate from staging)
# =============================================================================
# Each environment gets its own state file in S3 so they can be managed
# independently. Production can exist without staging.
#
# STATE FILE PATH:
#   s3://yr4-project-tf-state/production/terraform.tfstate
# =============================================================================

terraform {
  backend "s3" {
    bucket         = "yr4-project-tf-state"
    key            = "production/terraform.tfstate"
    region         = "eu-west-1"
    dynamodb_table = "yr4-project-terraform-locks"
    encrypt        = true
  }
}
