# =============================================================================
# Backend Configuration - Where Terraform stores its state file
# =============================================================================
#
# Instead of storing terraform.tfstate on your laptop (risky - could be lost or
# cause conflicts if two people run apply simultaneously), we store it in S3.
#
# HOW IT WORKS:
#   1. Terraform writes the state file to S3 after every apply
#   2. Before running, it acquires a lock in DynamoDB (prevents two people from
#      running apply at the same time)
#   3. The state file is encrypted at rest in S3 (encrypt = true)
#
# IMPORTANT: The S3 bucket and DynamoDB table must ALREADY EXIST before you can
# run "terraform init" with this backend. That's what the bootstrap/ module does.
# See: ../bootstrap/main.tf
#
# STATE FILE PATH:
#   s3://yr4-project-tf-state/infra/terraform.tfstate
#   The "key" is the path within the bucket. Using "infra/" prefix keeps it tidy
#   if we ever add more state files (e.g. infra/bootstrap.tfstate).
# =============================================================================

terraform {
  backend "s3" {
    bucket         = "yr4-project-tf-state"        # Created by bootstrap/main.tf
    key            = "infra/terraform.tfstate"     # Path within the bucket
    region         = "eu-west-1"                   # Must match the bucket's region
    dynamodb_table = "yr4-project-terraform-locks" # Created by bootstrap/main.tf
    encrypt        = true                          # AES-256 encryption at rest
  }
}
