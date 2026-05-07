# =============================================================================
# Production Environment - Outputs
# =============================================================================

# -- EKS ---------------------------------------------------------------------

output "cluster_name" {
  description = "Production EKS cluster name"
  value       = module.eks.cluster_name
}

output "cluster_endpoint" {
  description = "Production EKS API server URL"
  value       = module.eks.cluster_endpoint
}

output "cluster_ca_certificate" {
  description = "Production EKS CA cert (base64)"
  value       = module.eks.cluster_ca_certificate
  sensitive   = true
}

output "node_group_name" {
  description = "Production node group name"
  value       = module.eks.node_group_name
}

# -- RDS ---------------------------------------------------------------------

output "rds_endpoint" {
  description = "Production RDS endpoint (host:port)"
  value       = module.rds.endpoint
}

output "rds_address" {
  description = "Production RDS hostname"
  value       = module.rds.address
}

# -- Redis --------------------------------------------------------------------

output "redis_endpoint" {
  description = "Production Redis endpoint"
  value       = module.elasticache.endpoint
}

# -- VPC ---------------------------------------------------------------------

output "vpc_id" {
  description = "Production VPC ID"
  value       = module.vpc.vpc_id
}

# -- IAM (IRSA) ---------------------------------------------------------------

output "eso_role_arn" {
  description = "IAM role ARN for External Secrets Operator"
  value       = module.iam.eso_role_arn
}

output "alb_controller_role_arn" {
  description = "IAM role ARN for AWS Load Balancer Controller"
  value       = module.iam.alb_controller_role_arn
}

output "fluent_bit_role_arn" {
  description = "IAM role ARN for Fluent Bit CloudWatch Logs access"
  value       = module.iam.fluent_bit_role_arn
}

output "ebs_csi_driver_role_arn" {
  description = "IAM role ARN for the AWS EBS CSI driver addon"
  value       = module.iam.ebs_csi_driver_role_arn
}

# -- Observability -----------------------------------------------------------

output "cloudwatch_app_log_group_name" {
  description = "CloudWatch log group for application and gateway logs collected by Fluent Bit"
  value       = aws_cloudwatch_log_group.app_logs.name
}

output "cloudwatch_app_log_retention_days" {
  description = "Retention in days for application and gateway logs"
  value       = aws_cloudwatch_log_group.app_logs.retention_in_days
}

output "cloudwatch_cluster_log_group_name" {
  description = "CloudWatch log group for EKS control-plane logs"
  value       = aws_cloudwatch_log_group.eks_cluster.name
}

output "cloudwatch_cluster_log_retention_days" {
  description = "Retention in days for EKS control-plane logs"
  value       = aws_cloudwatch_log_group.eks_cluster.retention_in_days
}

output "cloudwatch_observability_addon_name" {
  description = "Amazon CloudWatch Observability EKS add-on name, or null when disabled"
  value       = module.eks.cloudwatch_observability_addon_name
}
