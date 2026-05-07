# =============================================================================
# Root Module - Input Variables
# =============================================================================
# These are the "knobs" you can turn to customise the infrastructure.
# Values come from (in order of precedence):
#   1. Command line:      terraform apply -var="node_desired_size=3"
#   2. Environment vars:  TF_VAR_rds_password=secret
#   3. terraform.tfvars:  the defaults file committed to the repo
#   4. default = "...":   the fallback defined right here in this file
#
# SENSITIVE VARIABLES:
#   rds_username and rds_password have NO defaults - they MUST be provided
#   via environment variables (TF_VAR_rds_username / TF_VAR_rds_password)
#   or via CI/CD masked variables. This prevents secrets from being in code.
# =============================================================================

# =============================================================================
# General - Project-wide settings
# =============================================================================

variable "aws_region" {
  description = "AWS region to deploy into"
  type        = string
  default     = "eu-west-1" # Ireland - closest EU region, good latency for Ireland-based project
}

variable "project_name" {
  description = "Project name - used as prefix for ALL resource names (e.g. yr4-project-eks, yr4-project-rds)"
  type        = string
  default     = "yr4-project"
}

variable "vpc_cidr" {
  description = "VPC CIDR block - /16 gives 65,536 IPs, more than enough for our cluster"
  type        = string
  default     = "10.0.0.0/16"
}

# =============================================================================
# EKS - Kubernetes cluster sizing
# =============================================================================

variable "kubernetes_version" {
  description = "Kubernetes version for EKS (check AWS docs for supported versions)"
  type        = string
  default     = "1.31" # Latest stable at time of writing
}

variable "node_instance_type" {
  description = "EC2 instance type for worker nodes - t3.medium (2 vCPU, 4GB) fits all 12 services"
  type        = string
  default     = "t3.medium"
}

variable "node_desired_size" {
  description = "How many worker nodes to run normally (2 nodes for redundancy across AZs)"
  type        = number
  default     = 2
}

variable "node_min_size" {
  description = "Minimum nodes - 0 allows scaling down completely when not in use (saves ~$3/day)"
  type        = number
  default     = 0
}

variable "node_max_size" {
  description = "Maximum nodes - 4 provides headroom for load spikes or demos"
  type        = number
  default     = 4
}

# =============================================================================
# RDS PostgreSQL - Database configuration
# =============================================================================

variable "rds_instance_class" {
  description = "RDS instance size - db.t3.micro (2 vCPU, 1GB) is the smallest available"
  type        = string
  default     = "db.t3.micro"
}

variable "rds_allocated_storage" {
  description = "Storage in GB - 20GB is the minimum; can grow automatically if needed"
  type        = number
  default     = 20
}

variable "rds_db_name" {
  description = "Default database created on the RDS instance (migration-runner creates schema)"
  type        = string
  default     = "crm_calendar"
}

variable "rds_username" {
  description = "Master DB username - MUST be set via TF_VAR_rds_username (no default = forces you to provide it)"
  type        = string
  sensitive   = true # Hidden in terraform plan/apply output
}

variable "rds_password" {
  description = "Master DB password - MUST be set via TF_VAR_rds_password (no default = forces you to provide it)"
  type        = string
  sensitive   = true # Hidden in terraform plan/apply output
}

# =============================================================================
# ElastiCache Redis - Cache and session configuration
# =============================================================================

variable "redis_node_type" {
  description = "Redis node size - cache.t3.micro (2 vCPU, 0.5GB) is sufficient for sessions + cache"
  type        = string
  default     = "cache.t3.micro"
}

# =============================================================================
# Secrets Manager - Application secrets (from TF_VAR_* env vars)
# =============================================================================
# These MUST be set via environment variables. No defaults = forces you to provide them.
#   TF_VAR_secret_key=$(openssl rand -hex 64)
#   TF_VAR_notification_encryption_key=$(python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
#   TF_VAR_google_maps_server_key=your-restricted-server-key
#   TF_VAR_google_maps_browser_key=your-restricted-browser-key

variable "secret_key" {
  description = "JWT signing key - MUST be set via TF_VAR_secret_key"
  type        = string
  sensitive   = true
}

variable "notification_encryption_key" {
  description = "Fernet encryption key for notification credentials - MUST be set via TF_VAR_notification_encryption_key"
  type        = string
  sensitive   = true
}

variable "google_maps_server_key" {
  description = "Google Maps Geocoding API key (server-side) - MUST be set via TF_VAR_google_maps_server_key"
  type        = string
  sensitive   = true
}

variable "google_maps_browser_key" {
  description = "Google Maps JavaScript API key (browser-side) - MUST be set via TF_VAR_google_maps_browser_key"
  type        = string
  sensitive   = true
}

variable "google_maps_map_id" {
  description = "Google Maps Map ID for styled maps - set via TF_VAR_google_maps_map_id"
  type        = string
  default     = ""
}
