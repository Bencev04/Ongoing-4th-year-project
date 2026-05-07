# =============================================================================
# Production Environment - Orchestrator
# =============================================================================
#
# Creates a SEPARATE EKS cluster, RDS, and ElastiCache for production.
# This is completely independent from the staging environment.
#
# ARCHITECTURE:
#   VPC → IAM → EKS → RDS → ElastiCache (same module composition as staging)
#
# DIFFERENCES FROM STAGING:
#   - More worker nodes (3 desired, max 5 vs 2/3 for staging)
#   - Larger RDS (db.t3.small vs db.t3.micro)
#   - Different VPC CIDR (10.1.0.0/16 vs 10.0.0.0/16)
#   - Separate S3 state key (production/terraform.tfstate)
#
# LIFECYCLE:
#   Production is brought up AFTER staging validation succeeds.
#   Staging is destroyed after successful promotion to production.
#   Production stays alive until manually torn down.
# =============================================================================

locals {
  cluster_name = "${var.project_name}-${var.environment}-eks"

  logs_environment       = "prod"
  app_log_group_name     = "/aws/eks/year4-project/${local.logs_environment}/logs"
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
  secrets_path_prefix = var.project_name # "yr4-project" - matches yr4-project/prod/* secret paths
  fluent_bit_log_group_names = [
    local.app_log_group_name,
  ]
  enable_cloudwatch_observability = var.enable_cloudwatch_observability
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
# 6. Infrastructure Secrets (DB + Redis credentials in Secrets Manager)
# =============================================================================
# This environment can either:
# - read pre-existing secret containers by name, or
# - create/manage the secret containers itself.

locals {
  secrets_env = "prod" # Short name matching K8s ExternalSecret paths
}

data "aws_secretsmanager_secret" "db_credentials" {
  count = var.use_existing_infra_secrets ? 1 : 0
  name  = "${var.project_name}/${local.secrets_env}/db-credentials"
}

resource "aws_secretsmanager_secret" "db_credentials" {
  count                   = var.use_existing_infra_secrets ? 0 : 1
  name                    = "${var.project_name}/${local.secrets_env}/db-credentials"
  description             = "PostgreSQL credentials for production"
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
  name  = "${var.project_name}/${local.secrets_env}/redis-credentials"
}

resource "aws_secretsmanager_secret" "redis_credentials" {
  count                   = var.use_existing_infra_secrets ? 0 : 1
  name                    = "${var.project_name}/${local.secrets_env}/redis-credentials"
  description             = "Redis connection details for production"
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
