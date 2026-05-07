# =============================================================================
# Bootstrap Variables
# =============================================================================
# These configure the S3 bucket and DynamoDB table names for state storage.
# Defaults match the project naming convention. Only change these if you have
# a naming conflict (e.g. the S3 bucket name is taken by another AWS account).
# =============================================================================

variable "aws_region" {
  description = "AWS region for the state backend"
  type        = string
  default     = "eu-west-1" # Ireland - closest EU region, matches all other infra
}

variable "project_name" {
  description = "Project identifier"
  type        = string
  default     = "yr4-project"
}

variable "state_bucket_name" {
  description = "S3 bucket name for Terraform state (must be globally unique across all AWS accounts)"
  type        = string
  default     = "yr4-project-tf-state"
}

variable "lock_table_name" {
  description = "DynamoDB table name for state locking (prevents concurrent applies)"
  type        = string
  default     = "yr4-project-terraform-locks"
}
