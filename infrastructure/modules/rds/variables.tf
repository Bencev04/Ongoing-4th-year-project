# =============================================================================
# RDS Module - Input Variables
# =============================================================================

variable "project_name" {
  description = "Project name used for resource naming"
  type        = string
}

# --- Network inputs (from VPC and EKS modules) --------------------------------

variable "vpc_id" {
  description = "VPC ID - the RDS security group is created in this VPC"
  type        = string
}

variable "private_subnet_ids" {
  description = "Private subnet IDs - RDS is placed in private subnets (no internet access)"
  type        = list(string)
}

variable "eks_security_group_id" {
  description = "EKS cluster security group ID - only this SG can connect to RDS on port 5432"
  type        = string
}

# --- Database configuration --------------------------------------------------

variable "engine_version" {
  description = "PostgreSQL engine version (major version only, e.g. '15')"
  type        = string
  default     = "15" # Latest stable at time of writing
}

variable "instance_class" {
  description = "RDS instance class - determines CPU and RAM"
  type        = string
  default     = "db.t3.micro" # 2 vCPU, 1GB RAM - smallest, good for low-traffic college project
}

variable "allocated_storage" {
  description = "Storage in GB - 20GB is the minimum for gp2 storage type"
  type        = number
  default     = 20
}

variable "db_name" {
  description = "Default database name created on launch (staging/prod use separate DBs within this instance)"
  type        = string
  default     = "crm_calendar" # The migration-runner service creates the actual schema
}

variable "db_username" {
  description = "Master database username - set via TF_VAR_rds_username env var, NEVER hardcode"
  type        = string
  sensitive   = true # Terraform will hide this in plan/apply output
}

variable "db_password" {
  description = "Master database password - set via TF_VAR_rds_password env var, NEVER hardcode"
  type        = string
  sensitive   = true # Terraform will hide this in plan/apply output
}

variable "tags" {
  description = "Common tags applied to all resources"
  type        = map(string)
  default     = {}
}
