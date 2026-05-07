# =============================================================================
# Staging Environment - Orchestrator
# =============================================================================
#
# Creates a SEPARATE EKS cluster, RDS, and ElastiCache for staging.
# This is completely independent from the production environment.
#
# ARCHITECTURE:
#   VPC → IAM → EKS → RDS → ElastiCache (same module composition as root)
#
# DIFFERENCES FROM PRODUCTION:
#   - Smaller node group (2 nodes max 3, vs 3 nodes max 5)
#   - Smaller RDS (db.t3.micro vs db.t3.small)
#   - Single-AZ database (no Multi-AZ - not needed for staging)
#   - Separate VPC CIDR space to avoid conflicts if peered
#   - Separate S3 state key (staging/terraform.tfstate)
#
# LIFECYCLE:
#   Staging is EPHEMERAL - it's created before CD validation and destroyed
#   after the validated image is promoted to production.
# =============================================================================

locals {
  cluster_name = "${var.project_name}-${var.environment}-eks"

  app_log_group_name     = "/aws/eks/year4-project/${var.environment}/logs"
  cluster_log_group_name = "/aws/eks/${local.cluster_name}/cluster"

  common_tags = {
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "terraform"
  }

  default_eks_admin_principal_arns = [
    "arn:aws:iam::${data.aws_caller_identity.current.account_id}:root",
    data.aws_caller_identity.current.arn, # Explicit entry for the CI runner IAM user
  ]

  effective_eks_admin_principal_arns = distinct(
    concat(local.default_eks_admin_principal_arns, var.additional_eks_admin_principal_arns),
  )

  eks_admin_access_entries = {
    for arn in local.effective_eks_admin_principal_arns :
    replace(replace(arn, ":", "_"), "/", "_") => {
      principal_arn           = arn
      policy_arn              = "arn:aws:eks::aws:cluster-access-policy/AmazonEKSClusterAdminPolicy"
      access_scope_type       = "cluster"
      access_scope_namespaces = []
      type                    = "STANDARD"
      kubernetes_groups       = []
    }
  }
}

data "aws_caller_identity" "current" {}

resource "aws_cloudwatch_log_group" "eks_cluster" {
  name              = local.cluster_log_group_name
  retention_in_days = var.cloudwatch_cluster_log_retention_days

  tags = merge(local.common_tags, { LogType = "eks-control-plane" })
}

resource "aws_cloudwatch_log_group" "app_logs" {
  name              = local.app_log_group_name
  retention_in_days = var.cloudwatch_app_log_retention_days

  tags = merge(local.common_tags, { LogType = "application" })
}

module "observability" {
  source = "../../../modules/observability"

  project_name              = var.project_name
  environment               = var.environment
  loki_bucket_name          = var.loki_bucket_name
  loki_bucket_force_destroy = var.loki_bucket_force_destroy
  loki_retention_days       = var.loki_retention_days
  create_loki_kms_key       = var.create_loki_kms_key
  tags                      = local.common_tags
}

# 1. VPC
module "vpc" {
  source = "../../../modules/vpc"

  project_name = "${var.project_name}-${var.environment}"
  cluster_name = local.cluster_name
  vpc_cidr     = var.vpc_cidr
  tags         = local.common_tags
}

# 2. IAM
module "iam" {
  source = "../../../modules/iam"

  project_name        = "${var.project_name}-${var.environment}"
  secrets_path_prefix = var.project_name # "yr4-project" - matches yr4-project/staging/* secret paths
  fluent_bit_log_group_names = [
    local.app_log_group_name,
  ]
  enable_cloudwatch_observability = var.enable_cloudwatch_observability
  loki_s3_bucket_arns             = [module.observability.loki_bucket_arn]
  loki_kms_key_arns               = module.observability.loki_kms_key_arn != "" ? [module.observability.loki_kms_key_arn] : []
  oidc_provider_arn               = module.eks.oidc_provider_arn
  oidc_provider_url               = module.eks.oidc_provider_url
  tags                            = local.common_tags
}

# 3. EKS
module "eks" {
  source = "../../../modules/eks"

  cluster_name        = local.cluster_name
  kubernetes_version  = var.kubernetes_version
  authentication_mode = "API_AND_CONFIG_MAP"
  access_entries      = local.eks_admin_access_entries

  vpc_id             = module.vpc.vpc_id
  public_subnet_ids  = module.vpc.public_subnet_ids
  private_subnet_ids = module.vpc.private_subnet_ids

  cluster_role_arn          = module.iam.eks_cluster_role_arn
  node_role_arn             = module.iam.eks_node_role_arn
  ebs_csi_driver_role_arn   = module.iam.ebs_csi_driver_role_arn
  enabled_cluster_log_types = var.enabled_cluster_log_types

  enable_cloudwatch_observability        = var.enable_cloudwatch_observability
  cloudwatch_observability_addon_version = var.cloudwatch_observability_addon_version

  node_instance_type = var.node_instance_type
  node_desired_size  = var.enabled ? var.node_desired_size : 0
  node_min_size      = var.node_min_size
  node_max_size      = var.node_max_size

  tags = local.common_tags

  depends_on = [aws_cloudwatch_log_group.eks_cluster]
}

# 4. RDS
module "rds" {
  source = "../../../modules/rds"

  project_name          = "${var.project_name}-${var.environment}"
  vpc_id                = module.vpc.vpc_id
  private_subnet_ids    = module.vpc.private_subnet_ids
  eks_security_group_id = module.eks.node_security_group_id

  instance_class    = var.rds_instance_class
  allocated_storage = var.rds_allocated_storage
  db_name           = var.rds_db_name
  db_username       = var.rds_username
  db_password       = var.rds_password

  tags = local.common_tags
}

# 5. ElastiCache
module "elasticache" {
  source = "../../../modules/elasticache"

  project_name          = "${var.project_name}-${var.environment}"
  vpc_id                = module.vpc.vpc_id
  private_subnet_ids    = module.vpc.private_subnet_ids
  eks_security_group_id = module.eks.node_security_group_id

  node_type = var.redis_node_type

  tags = local.common_tags
}

# =============================================================================
# 6. Staging Observability Alarms
# =============================================================================

resource "aws_sns_topic" "observability_alerts" {
  name = "${var.project_name}-${var.environment}-observability-alerts"

  tags = merge(local.common_tags, { Component = "observability" })
}

resource "aws_sns_topic_subscription" "observability_email" {
  count = var.observability_alert_email != "" ? 1 : 0

  topic_arn = aws_sns_topic.observability_alerts.arn
  protocol  = "email"
  endpoint  = var.observability_alert_email
}

locals {
  observability_alarm_actions    = var.enable_observability_alarm_actions ? [aws_sns_topic.observability_alerts.arn] : []
  observability_metric_namespace = "Year4Project/Staging"
}

resource "aws_cloudwatch_metric_alarm" "rds_cpu_high" {
  alarm_name          = "${var.project_name}-${var.environment}-rds-cpu-high"
  alarm_description   = "RDS CPU utilization is high in staging."
  namespace           = "AWS/RDS"
  metric_name         = "CPUUtilization"
  statistic           = "Average"
  period              = 300
  evaluation_periods  = 2
  datapoints_to_alarm = 2
  comparison_operator = "GreaterThanThreshold"
  threshold           = var.rds_cpu_high_threshold_percent
  treat_missing_data  = "notBreaching"
  alarm_actions       = local.observability_alarm_actions
  ok_actions          = local.observability_alarm_actions

  dimensions = {
    DBInstanceIdentifier = module.rds.identifier
  }

  tags = merge(local.common_tags, { Component = "observability", Service = "rds" })
}

resource "aws_cloudwatch_metric_alarm" "rds_storage_low" {
  alarm_name          = "${var.project_name}-${var.environment}-rds-storage-low"
  alarm_description   = "RDS free storage is low in staging."
  namespace           = "AWS/RDS"
  metric_name         = "FreeStorageSpace"
  statistic           = "Average"
  period              = 300
  evaluation_periods  = 2
  datapoints_to_alarm = 2
  comparison_operator = "LessThanThreshold"
  threshold           = var.rds_free_storage_low_threshold_bytes
  treat_missing_data  = "notBreaching"
  alarm_actions       = local.observability_alarm_actions
  ok_actions          = local.observability_alarm_actions

  dimensions = {
    DBInstanceIdentifier = module.rds.identifier
  }

  tags = merge(local.common_tags, { Component = "observability", Service = "rds" })
}

resource "aws_cloudwatch_metric_alarm" "rds_connections_high" {
  alarm_name          = "${var.project_name}-${var.environment}-rds-connections-high"
  alarm_description   = "RDS connection count is high in staging."
  namespace           = "AWS/RDS"
  metric_name         = "DatabaseConnections"
  statistic           = "Average"
  period              = 300
  evaluation_periods  = 2
  datapoints_to_alarm = 2
  comparison_operator = "GreaterThanThreshold"
  threshold           = var.rds_connections_high_threshold
  treat_missing_data  = "notBreaching"
  alarm_actions       = local.observability_alarm_actions
  ok_actions          = local.observability_alarm_actions

  dimensions = {
    DBInstanceIdentifier = module.rds.identifier
  }

  tags = merge(local.common_tags, { Component = "observability", Service = "rds" })
}

resource "aws_cloudwatch_metric_alarm" "redis_cpu_high" {
  alarm_name          = "${var.project_name}-${var.environment}-redis-cpu-high"
  alarm_description   = "Redis CPU utilization is high in staging."
  namespace           = "AWS/ElastiCache"
  metric_name         = "CPUUtilization"
  statistic           = "Average"
  period              = 300
  evaluation_periods  = 2
  datapoints_to_alarm = 2
  comparison_operator = "GreaterThanThreshold"
  threshold           = var.redis_cpu_high_threshold_percent
  treat_missing_data  = "notBreaching"
  alarm_actions       = local.observability_alarm_actions
  ok_actions          = local.observability_alarm_actions

  dimensions = {
    ReplicationGroupId = module.elasticache.replication_group_id
  }

  tags = merge(local.common_tags, { Component = "observability", Service = "redis" })
}

resource "aws_cloudwatch_metric_alarm" "redis_memory_high" {
  alarm_name          = "${var.project_name}-${var.environment}-redis-memory-high"
  alarm_description   = "Redis memory usage is high in staging."
  namespace           = "AWS/ElastiCache"
  metric_name         = "DatabaseMemoryUsagePercentage"
  statistic           = "Average"
  period              = 300
  evaluation_periods  = 2
  datapoints_to_alarm = 2
  comparison_operator = "GreaterThanThreshold"
  threshold           = var.redis_memory_high_threshold_percent
  treat_missing_data  = "notBreaching"
  alarm_actions       = local.observability_alarm_actions
  ok_actions          = local.observability_alarm_actions

  dimensions = {
    ReplicationGroupId = module.elasticache.replication_group_id
  }

  tags = merge(local.common_tags, { Component = "observability", Service = "redis" })
}

resource "aws_cloudwatch_metric_alarm" "redis_evictions" {
  alarm_name          = "${var.project_name}-${var.environment}-redis-evictions"
  alarm_description   = "Redis evictions were observed in staging."
  namespace           = "AWS/ElastiCache"
  metric_name         = "Evictions"
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  datapoints_to_alarm = 1
  comparison_operator = "GreaterThanThreshold"
  threshold           = var.redis_evictions_threshold
  treat_missing_data  = "notBreaching"
  alarm_actions       = local.observability_alarm_actions
  ok_actions          = local.observability_alarm_actions

  dimensions = {
    ReplicationGroupId = module.elasticache.replication_group_id
  }

  tags = merge(local.common_tags, { Component = "observability", Service = "redis" })
}

resource "aws_cloudwatch_log_metric_filter" "app_error_logs" {
  name           = "${var.project_name}-${var.environment}-app-errors"
  log_group_name = aws_cloudwatch_log_group.app_logs.name
  pattern        = "ERROR"

  metric_transformation {
    name      = "ApplicationErrorCount"
    namespace = local.observability_metric_namespace
    value     = "1"
  }
}

resource "aws_cloudwatch_metric_alarm" "app_error_logs_high" {
  alarm_name          = "${var.project_name}-${var.environment}-app-error-logs-high"
  alarm_description   = "Application error logs are elevated in staging."
  namespace           = local.observability_metric_namespace
  metric_name         = "ApplicationErrorCount"
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  datapoints_to_alarm = 1
  comparison_operator = "GreaterThanThreshold"
  threshold           = var.app_error_logs_high_threshold
  treat_missing_data  = "notBreaching"
  alarm_actions       = local.observability_alarm_actions
  ok_actions          = local.observability_alarm_actions

  tags = merge(local.common_tags, { Component = "observability", Service = "application" })
}

# =============================================================================
# 7. Infrastructure Secrets (DB + Redis credentials in Secrets Manager)
# =============================================================================
# This environment can either:
# - read pre-existing secret containers by name, or
# - create/manage the secret containers itself.

data "aws_secretsmanager_secret" "db_credentials" {
  count = var.use_existing_infra_secrets ? 1 : 0
  name  = "${var.project_name}/${var.environment}/db-credentials"
}

resource "aws_secretsmanager_secret" "db_credentials" {
  count                   = var.use_existing_infra_secrets ? 0 : 1
  name                    = "${var.project_name}/${var.environment}/db-credentials"
  description             = "PostgreSQL credentials for ${var.environment}"
  recovery_window_in_days = 0

  tags = merge(local.common_tags, { SecretType = "db-credentials" })
}

resource "aws_secretsmanager_secret_version" "db_credentials" {
  secret_id = var.use_existing_infra_secrets ? data.aws_secretsmanager_secret.db_credentials[0].id : aws_secretsmanager_secret.db_credentials[0].id
  secret_string = jsonencode({
    host         = module.rds.address
    port         = tostring(module.rds.port)
    username     = var.rds_username
    password     = var.rds_password
    database     = var.rds_db_name
    DATABASE_URL = "postgresql+asyncpg://${var.rds_username}:${var.rds_password}@${module.rds.address}:${module.rds.port}/${var.rds_db_name}"
  })
}

data "aws_secretsmanager_secret" "redis_credentials" {
  count = var.use_existing_infra_secrets ? 1 : 0
  name  = "${var.project_name}/${var.environment}/redis-credentials"
}

resource "aws_secretsmanager_secret" "redis_credentials" {
  count                   = var.use_existing_infra_secrets ? 0 : 1
  name                    = "${var.project_name}/${var.environment}/redis-credentials"
  description             = "Redis connection details for ${var.environment}"
  recovery_window_in_days = 0

  tags = merge(local.common_tags, { SecretType = "redis-credentials" })
}

resource "aws_secretsmanager_secret_version" "redis_credentials" {
  secret_id = var.use_existing_infra_secrets ? data.aws_secretsmanager_secret.redis_credentials[0].id : aws_secretsmanager_secret.redis_credentials[0].id
  secret_string = jsonencode({
    host                   = module.elasticache.endpoint
    port                   = tostring(module.elasticache.port)
    REDIS_URL              = "redis://${module.elasticache.endpoint}:${module.elasticache.port}"
    ADMIN_BL_REDIS_URL     = "redis://${module.elasticache.endpoint}:${module.elasticache.port}/0"
    AUTH_REDIS_URL         = "redis://${module.elasticache.endpoint}:${module.elasticache.port}/1"
    CUSTOMER_BL_REDIS_URL  = "redis://${module.elasticache.endpoint}:${module.elasticache.port}/2"
    JOB_BL_REDIS_URL       = "redis://${module.elasticache.endpoint}:${module.elasticache.port}/3"
    MAPS_REDIS_URL         = "redis://${module.elasticache.endpoint}:${module.elasticache.port}/4"
    NOTIFICATION_REDIS_URL = "redis://${module.elasticache.endpoint}:${module.elasticache.port}/5"
    USER_BL_REDIS_URL      = "redis://${module.elasticache.endpoint}:${module.elasticache.port}/6"
  })
}
