# =============================================================================
# Persistent Layer - Always-On Secrets Manager Secrets
# =============================================================================
#
# Creates app-secrets and api-keys for BOTH environments. These contain
# values that don't depend on infrastructure (no RDS/Redis endpoints).
#
# COST: ~$0.40/secret/month × 4 secrets = ~$1.60/month
#
# Infrastructure-dependent secrets (db-credentials, redis-credentials) are
# created by each environment's Terraform config alongside RDS/ElastiCache.
#
# SECRET LAYOUT:
#   yr4-project/staging/app-secrets  → SECRET_KEY, NOTIFICATION_ENCRYPTION_KEY
#   yr4-project/staging/api-keys     → GOOGLE_MAPS_SERVER_KEY, GOOGLE_MAPS_BROWSER_KEY
#   yr4-project/prod/app-secrets     → SECRET_KEY, NOTIFICATION_ENCRYPTION_KEY
#   yr4-project/prod/api-keys        → GOOGLE_MAPS_SERVER_KEY, GOOGLE_MAPS_BROWSER_KEY
# =============================================================================

locals {
  # "staging" and "prod" match the ExternalSecret paths in K8s overlays
  environments = ["staging", "prod"]
}

# =============================================================================
# 1. App Secrets (SECRET_KEY, NOTIFICATION_ENCRYPTION_KEY)
# =============================================================================

resource "aws_secretsmanager_secret" "app_secrets" {
  for_each = toset(local.environments)

  name        = "${var.project_name}/${each.value}/app-secrets"
  description = "Application secrets for ${each.value} environment"

  tags = {
    Environment = each.value
    SecretType  = "app-secrets"
  }
}

resource "aws_secretsmanager_secret_version" "app_secrets" {
  for_each = toset(local.environments)

  secret_id = aws_secretsmanager_secret.app_secrets[each.value].id
  secret_string = jsonencode({
    SECRET_KEY                  = var.secret_key
    NOTIFICATION_ENCRYPTION_KEY = var.notification_encryption_key
  })
}

# =============================================================================
# 2. API Keys (Google Maps)
# =============================================================================

resource "aws_secretsmanager_secret" "api_keys" {
  for_each = toset(local.environments)

  name        = "${var.project_name}/${each.value}/api-keys"
  description = "External API keys for ${each.value} environment"

  tags = {
    Environment = each.value
    SecretType  = "api-keys"
  }
}

resource "aws_secretsmanager_secret_version" "api_keys" {
  for_each = toset(local.environments)

  secret_id = aws_secretsmanager_secret.api_keys[each.value].id
  secret_string = jsonencode({
    GOOGLE_MAPS_SERVER_KEY  = var.google_maps_server_key
    GOOGLE_MAPS_BROWSER_KEY = var.google_maps_browser_key
    GOOGLE_MAPS_MAP_ID      = var.google_maps_map_id
  })
}

# =============================================================================
# 3. SMTP Secrets (empty placeholders — update via AWS Console/CLI when ready)
# =============================================================================

resource "aws_secretsmanager_secret" "smtp_secrets" {
  for_each = toset(local.environments)

  name        = "${var.project_name}/${each.value}/smtp-secrets"
  description = "SMTP credentials for ${each.value} notification service"

  tags = {
    Environment = each.value
    SecretType  = "smtp-secrets"
  }
}

resource "aws_secretsmanager_secret_version" "smtp_secrets" {
  for_each = toset(local.environments)

  secret_id = aws_secretsmanager_secret.smtp_secrets[each.value].id
  secret_string = jsonencode({
    SMTP_USERNAME = ""
    SMTP_PASSWORD = ""
  })
}
