# =============================================================================
# VPC Module - Input Variables
# =============================================================================
# These are the inputs the root module (terraform/main.tf) passes in when
# calling `module "vpc"`. They control the network layout.
# =============================================================================

variable "vpc_cidr" {
  description = "CIDR block for the VPC - defines the IP range for ALL subnets"
  type        = string
  default     = "10.0.0.0/16" # Gives 65,536 IPs - more than enough for our setup
}

variable "project_name" {
  description = "Project name used for resource naming (e.g. 'yr4-project')"
  type        = string
}

variable "cluster_name" {
  description = "EKS cluster name - used in subnet tags so EKS can auto-discover which subnets to use"
  type        = string
}

variable "tags" {
  description = "Common tags applied to all resources (Project, Environment, ManagedBy etc.)"
  type        = map(string)
  default     = {}
}
