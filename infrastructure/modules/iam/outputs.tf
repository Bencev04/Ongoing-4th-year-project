# =============================================================================
# IAM Module - Outputs
# =============================================================================
# These role ARNs are passed to the EKS module (for cluster + node creation)
# and to the ALB controller Helm chart (for IRSA annotation).
# =============================================================================

output "eks_cluster_role_arn" {
  description = "IAM role ARN for the EKS cluster control plane"
  value       = aws_iam_role.eks_cluster.arn
}

output "eks_node_role_arn" {
  description = "IAM role ARN for EKS worker node group EC2 instances"
  value       = aws_iam_role.eks_nodes.arn
}

output "alb_controller_role_arn" {
  description = "IAM role ARN for the AWS Load Balancer Controller (used in Helm values as IRSA annotation)"
  value       = aws_iam_role.alb_controller.arn
}

output "eso_role_arn" {
  description = "IAM role ARN for the External Secrets Operator (used in ESO Helm values as IRSA annotation)"
  value       = aws_iam_role.eso.arn
}

output "fluent_bit_role_arn" {
  description = "IAM role ARN for Fluent Bit CloudWatch Logs access"
  value       = aws_iam_role.fluent_bit.arn

  depends_on = [aws_iam_role_policy_attachment.fluent_bit_cloudwatch]
}

output "ebs_csi_driver_role_arn" {
  description = "IAM role ARN for the AWS EBS CSI driver addon"
  value       = aws_iam_role.ebs_csi_driver.arn

  depends_on = [aws_iam_role_policy_attachment.ebs_csi_driver]
}

output "loki_role_arn" {
  description = "IAM role ARN for Loki S3 object storage access"
  value       = aws_iam_role.loki.arn
}
