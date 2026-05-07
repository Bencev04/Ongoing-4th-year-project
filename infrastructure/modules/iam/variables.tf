# =============================================================================
# IAM Module - Input Variables
# =============================================================================

variable "project_name" {
  description = "Project name used for resource naming (e.g. 'yr4-project')"
  type        = string
}

# These two variables come from the EKS module outputs.
# They default to "" because there's a circular dependency:
#   IAM needs OIDC info from EKS, but EKS needs IAM roles to be created first.
# Terraform resolves this with a two-phase apply - first pass creates the roles
# with empty OIDC values, second pass (or same apply) fills them in.

variable "oidc_provider_arn" {
  description = "EKS OIDC provider ARN - needed to set up IRSA trust policies"
  type        = string
  default     = "" # Filled in after EKS cluster is created
}

variable "oidc_provider_url" {
  description = "EKS OIDC provider URL (without https://) - used in IRSA condition keys"
  type        = string
  default     = "" # Filled in after EKS cluster is created
}

variable "tags" {
  description = "Common tags applied to all resources"
  type        = map(string)
  default     = {}
}

variable "secrets_path_prefix" {
  description = "Secrets Manager path prefix for ESO access policy (e.g. yr4-project). If empty, uses project_name."
  type        = string
  default     = ""
}

variable "fluent_bit_namespace" {
  description = "Kubernetes namespace for the Fluent Bit service account."
  type        = string
  default     = "logging"
}

variable "fluent_bit_service_account_name" {
  description = "Kubernetes service account name used by Fluent Bit."
  type        = string
  default     = "fluent-bit"
}

variable "fluent_bit_log_group_names" {
  description = "CloudWatch log group names Fluent Bit may write to."
  type        = list(string)
  default     = []
}

variable "enable_cloudwatch_observability" {
  description = "Whether to grant worker nodes permissions required by the Amazon CloudWatch Observability EKS add-on."
  type        = bool
  default     = false
}

variable "ebs_csi_service_account_name" {
  description = "Kubernetes service account name used by the AWS EBS CSI controller."
  type        = string
  default     = "ebs-csi-controller-sa"
}

variable "loki_namespace" {
  description = "Kubernetes namespace for the Loki service account."
  type        = string
  default     = "monitoring"
}

variable "loki_service_account_name" {
  description = "Kubernetes service account name used by Loki."
  type        = string
  default     = "loki"
}

variable "loki_s3_bucket_arns" {
  description = "S3 bucket ARNs Loki may use for object storage. If empty, only the IRSA role is created."
  type        = list(string)
  default     = []
}

variable "loki_kms_key_arns" {
  description = "KMS key ARNs Loki may use for encrypted S3 object storage."
  type        = list(string)
  default     = []
}
