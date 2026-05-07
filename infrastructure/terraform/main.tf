# ============================================================================
# Root Module - Wires all infrastructure modules together
# ============================================================================
#
# This is the "orchestrator" file. It doesn't create any resources directly.
# Instead, it calls our 5 child modules and passes values between them.
#
# ARCHITECTURE:
#   1. VPC module     → creates networking (subnets, NAT, routes)
#   2. IAM module     → creates IAM roles for EKS (cluster + nodes + LB controller)
#   3. EKS module     → creates the Kubernetes cluster and managed node group
#   4. RDS module     → creates PostgreSQL (uses VPC + EKS security group)
#   5. ElastiCache    → creates Redis (uses VPC + EKS security group)
#
# DEPENDENCY CHAIN (Terraform figures this out automatically):
#   VPC → EKS (needs subnets)
#   IAM → EKS (needs OIDC outputs)  [circular - resolved by IAM defaults]
#   EKS → RDS (needs security group)
#   EKS → ElastiCache (needs security group)
#
# SHARED INFRASTRUCTURE:
#   We use ONE of each resource (EKS, RDS, Redis) for both staging and prod.
#   Environments are separated by Kubernetes namespaces and database names.
#   This keeps costs low (~$5-10/day instead of ~$15-20/day for duplicates).
# ============================================================================

# =============================================================================
# Local Values - Computed constants used by multiple modules
# =============================================================================

locals {
  # Cluster name is derived from project name to keep naming consistent.
  # This name appears in: EKS console, kubectl config, VPC tags, etc.
  cluster_name = "${var.project_name}-eks"

  # Tags applied to EVERY resource created by every module.
  # These make it easy to:
  #   - Filter resources in the AWS console
  #   - Track costs in AWS Cost Explorer
  #   - Identify who/what created a resource
  common_tags = {
    Project     = var.project_name
    Environment = "shared"    # Not "staging" or "prod" because infra is shared
    ManagedBy   = "terraform" # So we know not to modify manually
  }
}

# =============================================================================
# 1. VPC Module - Networking foundation (must be created FIRST)
# =============================================================================
# Creates: VPC, subnets (2 public + 2 private), NAT gateway, route tables.
# Everything else runs INSIDE this VPC.

module "vpc" {
  source = "../modules/vpc"

  project_name = var.project_name
  cluster_name = local.cluster_name # Needed for kubernetes.io tags on subnets
  vpc_cidr     = var.vpc_cidr       # Default: 10.0.0.0/16
  tags         = local.common_tags
}

# =============================================================================
# 2. IAM Module - Permissions for EKS and its components
# =============================================================================
# Creates: Cluster role, node role, ALB controller role (with IRSA).
# NOTE: The OIDC values come FROM the EKS module - Terraform resolves this
# circular dependency because the IAM module has defaults for these variables.

module "iam" {
  source = "../modules/iam"

  project_name      = var.project_name
  oidc_provider_arn = module.eks.oidc_provider_arn # From EKS → enables IRSA
  oidc_provider_url = module.eks.oidc_provider_url # From EKS → used in trust policy
  tags              = local.common_tags
}

# =============================================================================
# 3. EKS Module - The Kubernetes cluster where our app runs
# =============================================================================
# Creates: EKS control plane, managed node group, OIDC provider, addons.
# Depends on: VPC (for subnets) and IAM (for role ARNs).

module "eks" {
  source = "../modules/eks"

  cluster_name       = local.cluster_name
  kubernetes_version = var.kubernetes_version # Default: "1.29"

  # Network inputs from VPC module
  vpc_id             = module.vpc.vpc_id
  public_subnet_ids  = module.vpc.public_subnet_ids  # For ALB/NLB
  private_subnet_ids = module.vpc.private_subnet_ids # For worker nodes

  # IAM roles from IAM module
  cluster_role_arn        = module.iam.eks_cluster_role_arn
  node_role_arn           = module.iam.eks_node_role_arn
  ebs_csi_driver_role_arn = module.iam.ebs_csi_driver_role_arn

  # Node group sizing (all configurable via terraform.tfvars)
  node_instance_type = var.node_instance_type # Default: t3.medium
  node_desired_size  = var.node_desired_size  # Default: 2
  node_min_size      = var.node_min_size      # Default: 0 (can scale to zero!)
  node_max_size      = var.node_max_size      # Default: 4

  tags = local.common_tags
}

# =============================================================================
# 4. RDS Module - PostgreSQL database
# =============================================================================
# Creates: DB subnet group, security group, RDS PostgreSQL instance.
# Depends on: VPC (for subnets and VPC ID) and EKS (for security group ID).
# The eks_security_group_id ensures only EKS pods can reach the database.

module "rds" {
  source = "../modules/rds"

  project_name          = var.project_name
  vpc_id                = module.vpc.vpc_id
  private_subnet_ids    = module.vpc.private_subnet_ids
  eks_security_group_id = module.eks.node_security_group_id # Only EKS pods can connect

  instance_class    = var.rds_instance_class    # Default: db.t3.micro
  allocated_storage = var.rds_allocated_storage # Default: 20 GB
  db_name           = var.rds_db_name           # Default: "crm_calendar"
  db_username       = var.rds_username          # From TF_VAR_rds_username
  db_password       = var.rds_password          # From TF_VAR_rds_password

  tags = local.common_tags
}

# =============================================================================
# 5. ElastiCache Module - Redis cache and session store
# =============================================================================
# Creates: Subnet group, security group, Redis replication group.
# Same dependency pattern as RDS: needs VPC subnets + EKS security group.

module "elasticache" {
  source = "../modules/elasticache"

  project_name          = var.project_name
  vpc_id                = module.vpc.vpc_id
  private_subnet_ids    = module.vpc.private_subnet_ids
  eks_security_group_id = module.eks.node_security_group_id # Only EKS pods can connect

  node_type = var.redis_node_type # Default: cache.t3.micro

  tags = local.common_tags
}

# =============================================================================
# 6. Secrets Module - AWS Secrets Manager
# =============================================================================
# Creates secrets in AWS Secrets Manager for each environment (staging + prod).
# Terraform writes the RDS/Redis endpoints INTO the secrets automatically.
# If RDS is destroyed and recreated, the next `terraform apply` updates the
# secrets with the new endpoint - External Secrets Operator syncs to K8s.
#
# Depends on: RDS (for address), ElastiCache (for endpoint), and TF_VAR_* env vars.

module "secrets" {
  source = "../modules/secrets"

  project_name = var.project_name
  environments = ["staging", "prod"]

  # Auto-populated from infrastructure outputs
  rds_address   = module.rds.address          # If RDS is recreated, this updates
  rds_port      = module.rds.port             # Always 5432
  redis_address = module.elasticache.endpoint # If Redis is recreated, this updates

  # Credentials (from TF_VAR_* environment variables)
  db_username = var.rds_username # From TF_VAR_rds_username
  db_password = var.rds_password # From TF_VAR_rds_password

  # Application secrets (from TF_VAR_* environment variables)
  secret_key                  = var.secret_key                  # From TF_VAR_secret_key
  notification_encryption_key = var.notification_encryption_key # From TF_VAR_notification_encryption_key

  # External API keys (from TF_VAR_* environment variables)
  google_maps_server_key  = var.google_maps_server_key  # From TF_VAR_google_maps_server_key
  google_maps_browser_key = var.google_maps_browser_key # From TF_VAR_google_maps_browser_key
  google_maps_map_id      = var.google_maps_map_id      # From TF_VAR_google_maps_map_id

  tags = local.common_tags
}
