# =============================================================================
# Root Module - Outputs
# =============================================================================
# After "terraform apply", these values are printed to the console and can also
# be retrieved later with "terraform output <name>".
#
# WHO USES THESE?
#   - GitLab CI/CD:  reads cluster_name and node_group_name to run kubectl
#                    and to scale nodes up/down
#   - ArgoCD:        connects to cluster_endpoint with cluster_ca_certificate
#   - Developers:    use rds_endpoint and redis_endpoint for debugging
#   - Kubernetes:    secrets reference rds_address and redis_endpoint
# =============================================================================

# =============================================================================
# EKS Cluster Outputs
# =============================================================================

output "cluster_name" {
  description = "EKS cluster name - used by: kubectl, aws eks update-kubeconfig, GitLab CI/CD"
  value       = module.eks.cluster_name
}

output "cluster_endpoint" {
  description = "EKS API server URL - used by: kubectl, ArgoCD, any K8s client"
  value       = module.eks.cluster_endpoint
}

output "cluster_ca_certificate" {
  description = "EKS CA cert (base64) - needed to verify the API server's TLS certificate"
  value       = module.eks.cluster_ca_certificate
  sensitive   = true # Hidden in output because it's a security credential
}

output "node_group_name" {
  description = "Node group name - used by GitLab CI/CD to scale nodes up (ensure job) and down (destroy job)"
  value       = module.eks.node_group_name
}

# =============================================================================
# RDS PostgreSQL Outputs
# =============================================================================

output "rds_endpoint" {
  description = "Full RDS endpoint (host:port) - e.g. yr4-project-postgres.xxxx.eu-west-1.rds.amazonaws.com:5432"
  value       = module.rds.endpoint
}

output "rds_address" {
  description = "RDS hostname only - used in Kubernetes secrets for DATABASE_HOST env var"
  value       = module.rds.address
}

# =============================================================================
# Redis Outputs
# =============================================================================

output "redis_endpoint" {
  description = "Redis endpoint - used in Kubernetes secrets for REDIS_HOST env var"
  value       = module.elasticache.endpoint
}

# =============================================================================
# VPC Outputs (for reference/debugging)
# =============================================================================

output "vpc_id" {
  description = "VPC ID - useful for AWS console navigation and debugging"
  value       = module.vpc.vpc_id
}

output "private_subnet_ids" {
  description = "Private subnet IDs - where EKS nodes, RDS, and Redis live"
  value       = module.vpc.private_subnet_ids
}

output "public_subnet_ids" {
  description = "Public subnet IDs - where the ALB (load balancer) lives"
  value       = module.vpc.public_subnet_ids
}

# =============================================================================
# Secrets Manager Outputs
# =============================================================================

output "secret_arns" {
  description = "All Secrets Manager ARNs - needed for IAM policy scoping"
  value       = module.secrets.all_secret_arns
}

output "eso_role_arn" {
  description = "IAM role ARN for the External Secrets Operator (annotate K8s ServiceAccount with this)"
  value       = module.iam.eso_role_arn
}

output "fluent_bit_role_arn" {
  description = "IAM role ARN for Fluent Bit CloudWatch Logs access"
  value       = module.iam.fluent_bit_role_arn
}

output "ebs_csi_driver_role_arn" {
  description = "IAM role ARN for the AWS EBS CSI driver addon"
  value       = module.iam.ebs_csi_driver_role_arn
}
