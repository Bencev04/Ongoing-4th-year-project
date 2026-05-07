# =============================================================================
# RDS Module - Outputs
# =============================================================================
# These values are needed to:
#   - Create Kubernetes secrets (so pods know where to connect)
#   - Configure the migration-runner service
#   - Debug connection issues
# =============================================================================

output "endpoint" {
  description = "RDS endpoint in host:port format (e.g. yr4-project-postgres.xxxx.eu-west-1.rds.amazonaws.com:5432)"
  value       = aws_db_instance.main.endpoint
}

output "address" {
  description = "RDS hostname only (without port) - used in K8s secrets and connection strings"
  value       = aws_db_instance.main.address
}

output "port" {
  description = "RDS port (always 5432 for PostgreSQL)"
  value       = aws_db_instance.main.port
}

output "db_name" {
  description = "Default database name created on the instance"
  value       = aws_db_instance.main.db_name
}

output "security_group_id" {
  description = "RDS security group ID (for reference/debugging)"
  value       = aws_security_group.rds.id
}

output "identifier" {
  description = "RDS DB instance identifier used for CloudWatch alarm dimensions"
  value       = aws_db_instance.main.identifier
}
