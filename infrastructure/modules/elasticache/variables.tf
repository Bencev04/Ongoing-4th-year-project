# =============================================================================
# ElastiCache Module - Input Variables
# =============================================================================

variable "project_name" {
  description = "Project name used for resource naming"
  type        = string
}

# --- Network inputs (from VPC and EKS modules) --------------------------------

variable "vpc_id" {
  description = "VPC ID - the Redis security group is created in this VPC"
  type        = string
}

variable "private_subnet_ids" {
  description = "Private subnet IDs - Redis is placed in private subnets (no internet access)"
  type        = list(string)
}

variable "eks_security_group_id" {
  description = "EKS cluster security group ID - only this SG can connect to Redis on port 6379"
  type        = string
}

# --- Redis configuration -----------------------------------------------------

variable "engine_version" {
  description = "Redis engine version (e.g. '7.0')"
  type        = string
  default     = "7.0" # Latest major version at time of writing
}

variable "node_type" {
  description = "ElastiCache node type - determines CPU, RAM, and network performance"
  type        = string
  default     = "cache.t3.micro" # 2 vCPU, 0.5GB RAM - sufficient for session store + cache
}

variable "tags" {
  description = "Common tags applied to all resources"
  type        = map(string)
  default     = {}
}
