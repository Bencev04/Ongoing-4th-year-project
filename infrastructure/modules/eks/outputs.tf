# =============================================================================
# EKS Module - Outputs
# =============================================================================
# These outputs are consumed by:
#   - The root module (terraform/outputs.tf) - exposed for kubectl/scripts
#   - The IAM module - OIDC provider for IRSA roles
#   - The RDS/ElastiCache modules - cluster security group for ingress rules
# =============================================================================

output "cluster_name" {
  description = "EKS cluster name - used by kubectl, aws eks commands, and scripts"
  value       = aws_eks_cluster.main.name
}

output "cluster_endpoint" {
  description = "EKS cluster API endpoint URL - where kubectl sends requests"
  value       = aws_eks_cluster.main.endpoint
}

output "cluster_ca_certificate" {
  description = "EKS cluster CA certificate (base64) - used to verify the API server's identity"
  value       = aws_eks_cluster.main.certificate_authority[0].data
}

output "cluster_security_group_id" {
  description = "Custom cluster security group ID - attached to cluster ENIs only"
  value       = aws_security_group.cluster.id
}

output "node_security_group_id" {
  description = "EKS-managed cluster security group - shared by control plane AND managed node groups. Use this for RDS/Redis ingress rules."
  value       = aws_eks_cluster.main.vpc_config[0].cluster_security_group_id
}

output "oidc_provider_arn" {
  description = "OIDC provider ARN - passed to IAM module for IRSA trust policies"
  value       = aws_iam_openid_connect_provider.eks.arn
}

output "oidc_provider_url" {
  description = "OIDC provider URL (without https://) - used in IAM trust policy conditions"
  value       = replace(aws_eks_cluster.main.identity[0].oidc[0].issuer, "https://", "")
}

output "node_group_name" {
  description = "Managed node group name - needed for scale-up/scale-down commands"
  value       = aws_eks_node_group.main.node_group_name
}

output "ebs_csi_addon_name" {
  description = "EKS addon name for the AWS EBS CSI driver"
  value       = aws_eks_addon.ebs_csi.addon_name
}

output "cloudwatch_observability_addon_name" {
  description = "EKS addon name for Amazon CloudWatch Observability, or null when disabled"
  value       = try(aws_eks_addon.cloudwatch_observability[0].addon_name, null)
}
