# =============================================================================
# Persistent Layer - Outputs
# =============================================================================

output "app_secrets_arns" {
  description = "ARNs of app-secrets per environment"
  value       = { for env in local.environments : env => aws_secretsmanager_secret.app_secrets[env].arn }
}

output "api_keys_arns" {
  description = "ARNs of api-keys per environment"
  value       = { for env in local.environments : env => aws_secretsmanager_secret.api_keys[env].arn }
}
