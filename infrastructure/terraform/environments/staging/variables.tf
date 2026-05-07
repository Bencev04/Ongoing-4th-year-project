# =============================================================================
# Staging Environment - Input Variables
# =============================================================================

# -- General ------------------------------------------------------------------

variable "aws_region" {
  description = "AWS region to deploy into"
  type        = string
  default     = "eu-west-1"
}

variable "project_name" {
  description = "Project name - used as prefix for all resource names"
  type        = string
  default     = "yr4-project"
}

variable "environment" {
  description = "Environment name - used in resource naming and tagging"
  type        = string
  default     = "staging"
}

variable "vpc_cidr" {
  description = "VPC CIDR block"
  type        = string
  default     = "10.0.0.0/16"
}

# -- EKS ---------------------------------------------------------------------

variable "kubernetes_version" {
  description = "Kubernetes version for EKS"
  type        = string
  default     = "1.31"
}

variable "node_instance_type" {
  description = "EC2 instance type for worker nodes"
  type        = string
  default     = "t3.medium"
}

variable "node_desired_size" {
  description = "Desired number of worker nodes"
  type        = number
  default     = 2
}

variable "node_min_size" {
  description = "Minimum number of worker nodes (0 allows full scale-down)"
  type        = number
  default     = 0
}

variable "node_max_size" {
  description = "Maximum number of worker nodes"
  type        = number
  default     = 3
}

variable "additional_eks_admin_principal_arns" {
  description = "Extra IAM principal ARNs to grant cluster-admin access via EKS access entries"
  type        = list(string)
  default     = []
}

variable "enabled_cluster_log_types" {
  description = "EKS control-plane log types to send to CloudWatch."
  type        = list(string)
  default     = ["api", "audit", "authenticator", "controllerManager", "scheduler"]
}

variable "cloudwatch_cluster_log_retention_days" {
  description = "Retention in days for EKS control-plane CloudWatch logs."
  type        = number
  default     = 30
}

variable "cloudwatch_app_log_retention_days" {
  description = "Retention in days for Fluent Bit application CloudWatch logs."
  type        = number
  default     = 30
}

variable "enable_cloudwatch_observability" {
  description = "Whether to install the Amazon CloudWatch Observability EKS add-on for Container Insights in staging."
  type        = bool
  default     = true
}

variable "cloudwatch_observability_addon_version" {
  description = "Optional explicit version for the Amazon CloudWatch Observability EKS add-on. Leave null to use AWS default/latest compatible version."
  type        = string
  default     = null
}

variable "loki_bucket_name" {
  description = "Optional explicit S3 bucket name for Loki object storage. Leave empty for the default account-scoped name."
  type        = string
  default     = ""
}

variable "loki_bucket_force_destroy" {
  description = "Whether Terraform may delete the staging Loki bucket even when it contains objects."
  type        = bool
  default     = true
}

variable "loki_retention_days" {
  description = "Number of days to retain Loki chunks and index objects in S3."
  type        = number
  default     = 30
}

variable "create_loki_kms_key" {
  description = "Whether to create a dedicated KMS key for staging Loki S3 encryption."
  type        = bool
  default     = true
}

variable "observability_alert_email" {
  description = "Optional email address subscribed to the staging observability SNS topic. Leave empty to create the topic without email subscription."
  type        = string
  default     = ""
}

variable "enable_observability_alarm_actions" {
  description = "Whether staging observability alarms should publish to the SNS topic."
  type        = bool
  default     = true
}

variable "rds_cpu_high_threshold_percent" {
  description = "RDS CPU utilization percentage that triggers a staging alarm."
  type        = number
  default     = 80
}

variable "rds_free_storage_low_threshold_bytes" {
  description = "RDS free storage bytes threshold that triggers a staging alarm. Default is 5 GiB."
  type        = number
  default     = 5368709120
}

variable "rds_connections_high_threshold" {
  description = "RDS connection count that triggers a staging alarm."
  type        = number
  default     = 80
}

variable "redis_cpu_high_threshold_percent" {
  description = "Redis CPU utilization percentage that triggers a staging alarm."
  type        = number
  default     = 80
}

variable "redis_memory_high_threshold_percent" {
  description = "Redis memory usage percentage that triggers a staging alarm."
  type        = number
  default     = 80
}

variable "redis_evictions_threshold" {
  description = "Redis eviction count in a five-minute period that triggers a staging alarm."
  type        = number
  default     = 0
}

variable "app_error_logs_high_threshold" {
  description = "Application ERROR log count in a five-minute period that triggers a staging alarm."
  type        = number
  default     = 5
}

# -- RDS PostgreSQL -----------------------------------------------------------

variable "rds_instance_class" {
  description = "RDS instance size"
  type        = string
  default     = "db.t3.micro"
}

variable "rds_allocated_storage" {
  description = "Storage in GB"
  type        = number
  default     = 20
}

variable "rds_db_name" {
  description = "Default database name"
  type        = string
  default     = "crm_calendar_staging"
}

variable "rds_username" {
  description = "Master DB username - set via TF_VAR_rds_username"
  type        = string
  sensitive   = true
}

variable "rds_password" {
  description = "Master DB password - set via TF_VAR_rds_password"
  type        = string
  sensitive   = true
}

# -- ElastiCache Redis --------------------------------------------------------

variable "redis_node_type" {
  description = "Redis node size"
  type        = string
  default     = "cache.t3.micro"
}

# -- Feature flag - enable/disable entire environment -------------------------

variable "enabled" {
  description = "Set to false to scale nodes to 0 (keeps control plane alive)"
  type        = bool
  default     = true
}

variable "use_existing_infra_secrets" {
  description = "If true, read existing db/redis secret containers by name. If false, create and manage them in this stack."
  type        = bool
  default     = false
}
