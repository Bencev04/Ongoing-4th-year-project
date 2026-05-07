variable "project_name" {
  description = "Project name used for observability resource naming."
  type        = string
}

variable "environment" {
  description = "Environment name used for observability resource naming and tags."
  type        = string
}

variable "loki_bucket_name" {
  description = "Optional explicit S3 bucket name for Loki object storage. If empty, a deterministic account-scoped name is used."
  type        = string
  default     = ""
}

variable "loki_bucket_force_destroy" {
  description = "Whether Terraform may delete the Loki bucket even when it contains objects. Keep false outside disposable environments."
  type        = bool
  default     = false
}

variable "loki_retention_days" {
  description = "Number of days to retain Loki chunks and index objects in S3."
  type        = number
  default     = 30
}

variable "create_loki_kms_key" {
  description = "Whether to create a dedicated KMS key for Loki S3 encryption."
  type        = bool
  default     = true
}

variable "tags" {
  description = "Common tags applied to observability resources."
  type        = map(string)
  default     = {}
}
