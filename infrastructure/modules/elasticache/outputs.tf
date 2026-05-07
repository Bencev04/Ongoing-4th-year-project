# =============================================================================
# ElastiCache Module - Outputs
# =============================================================================
# These values are needed to:
#   - Create Kubernetes secrets (so pods know where to connect to Redis)
#   - Configure connection strings in service environment variables
# =============================================================================

output "endpoint" {
  description = "Redis primary endpoint address (e.g. yr4-project-redis.xxxx.cache.amazonaws.com)"
  value       = aws_elasticache_replication_group.main.primary_endpoint_address
}

output "port" {
  description = "Redis port (always 6379)"
  value       = 6379
}

output "security_group_id" {
  description = "Redis security group ID (for reference/debugging)"
  value       = aws_security_group.redis.id
}

output "replication_group_id" {
  description = "ElastiCache replication group ID used for CloudWatch alarm dimensions"
  value       = aws_elasticache_replication_group.main.replication_group_id
}
