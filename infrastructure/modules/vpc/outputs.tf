# =============================================================================
# VPC Module - Outputs
# =============================================================================
# These values are passed to other modules:
#   - vpc_id            → used by EKS, RDS, ElastiCache security groups
#   - public_subnet_ids → used by EKS cluster (for ALB placement)
#   - private_subnet_ids → used by EKS nodes, RDS subnet group, Redis subnet group
#   - vpc_cidr_block    → available for security group rules if needed
# =============================================================================

output "vpc_id" {
  description = "VPC ID - referenced by all other modules for security groups"
  value       = aws_vpc.main.id
}

output "public_subnet_ids" {
  description = "Public subnet IDs - where the ALB (load balancer) is placed"
  value       = aws_subnet.public[*].id
}

output "private_subnet_ids" {
  description = "Private subnet IDs - where EKS nodes, RDS, and Redis live"
  value       = aws_subnet.private[*].id
}

output "vpc_cidr_block" {
  description = "VPC CIDR block (10.0.0.0/16) - can be used in security group ingress rules"
  value       = aws_vpc.main.cidr_block
}
