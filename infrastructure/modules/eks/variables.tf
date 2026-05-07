# =============================================================================
# EKS Module - Input Variables
# =============================================================================

variable "cluster_name" {
  description = "Name of the EKS cluster (e.g. 'yr4-project-eks')"
  type        = string
}

variable "kubernetes_version" {
  description = "Kubernetes version for the EKS cluster (check AWS docs for supported versions)"
  type        = string
  default     = "1.31" # Latest LTS-like version at time of writing
}

variable "authentication_mode" {
  description = "EKS cluster authentication mode (CONFIG_MAP, API, or API_AND_CONFIG_MAP)"
  type        = string
  default     = "API_AND_CONFIG_MAP"
}

variable "access_entries" {
  description = "Map of EKS access entries and policy associations to create"
  type = map(object({
    principal_arn           = string
    policy_arn              = string
    access_scope_type       = string
    access_scope_namespaces = list(string)
    type                    = string
    kubernetes_groups       = list(string)
  }))
  default = {}
}

# --- Network inputs (from the VPC module) ------------------------------------

variable "vpc_id" {
  description = "VPC ID - the cluster's security group is created in this VPC"
  type        = string
}

variable "public_subnet_ids" {
  description = "Public subnet IDs - used for the EKS API endpoint and ALB"
  type        = list(string)
}

variable "private_subnet_ids" {
  description = "Private subnet IDs - where the worker nodes are placed"
  type        = list(string)
}

# --- IAM inputs (from the IAM module) ----------------------------------------

variable "cluster_role_arn" {
  description = "IAM role ARN for the EKS cluster (from iam module → eks_cluster_role_arn)"
  type        = string
}

variable "node_role_arn" {
  description = "IAM role ARN for the EKS node group (from iam module → eks_node_role_arn)"
  type        = string
}

variable "ebs_csi_driver_role_arn" {
  description = "IAM role ARN for the AWS EBS CSI driver service account."
  type        = string
  default     = null
}

variable "enabled_cluster_log_types" {
  description = "EKS control-plane log types to send to CloudWatch."
  type        = list(string)
  default     = []
}

variable "enable_cloudwatch_observability" {
  description = "Whether to install the Amazon CloudWatch Observability EKS add-on for Container Insights."
  type        = bool
  default     = false
}

variable "cloudwatch_observability_addon_version" {
  description = "Optional explicit version for the Amazon CloudWatch Observability EKS add-on. Leave null to use AWS default/latest compatible version."
  type        = string
  default     = null
}

# --- Node group sizing -------------------------------------------------------

variable "node_instance_type" {
  description = "EC2 instance type for worker nodes (t3.medium = 2 vCPU, 4GB RAM)"
  type        = string
  default     = "t3.medium" # Fits ~6 microservices per node (128MB each + system overhead)
}

variable "node_desired_size" {
  description = "How many worker nodes to run right now (set to 0 to stop all workloads)"
  type        = number
  default     = 2 # 2 nodes fit all 12 services with room for ArgoCD + system pods
}

variable "node_min_size" {
  description = "Minimum worker nodes - 0 allows full scale-down for cost saving"
  type        = number
  default     = 0 # IMPORTANT: 0 lets us scale down without destroying the cluster
}

variable "node_max_size" {
  description = "Maximum worker nodes - ceiling for scaling"
  type        = number
  default     = 4 # Enough for moderate load; increase if adding more services
}

variable "tags" {
  description = "Common tags applied to all resources"
  type        = map(string)
  default     = {}
}
